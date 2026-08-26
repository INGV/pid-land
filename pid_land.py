#!/usr/bin/python3
"""
============
# LEGAL-INFO
============
# Disclaimer:
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.
    This script is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY.

# Copyright:
    2023 Massimo Fares, INGV - Italy <massimo.fares@ingv.it>; EIDA Italia Team, INGV - Italy  <adaisacd.ont@ingv.it>

# License:
    GPLv3

# Platform:
    Linux

# Author:
    Massimo Fares, INGV - Italy <massimo.fares@ingv.it>
"""

import os
import yaml
import logging
import re
import tornado.ioloop
import tornado.web
import json
import io
from jsonschema import validate, ValidationError
from pyshacl import validate as shacl_validate
from rdflib import Graph
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from modules.provenance import Provenance
from modules.metadata import Metadata
from modules.cutter import Cutter
from obspy import read, UTCDateTime

from core.prism import Prism


# ---------------------------
# Config Loader
# ---------------------------
def load_config(path="pidland-config.yaml"):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f)

# ---------------------------
# Logger Setup
# ---------------------------
def setup_logger(config):
    log = logging.getLogger("PID-LAND")
    log.setLevel(getattr(logging, config.get("LOG_LEVEL", "INFO")))
    log.propagate = False
    log_dir = Path(config.get('LOG_DIR', './log'))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / config.get('LOG_FILE', 'pid_land.log')
    file_handler = TimedRotatingFileHandler(log_file, when="midnight")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    log.addHandler(file_handler)
    return log



# ---------------------------
# PID Resolver Handler
# ---------------------------
class ResolvePIDHandler(tornado.web.RequestHandler):
    def initialize(self, config, log, prov: Provenance, meta: Metadata):
        self.config = config
        self.log = log
        self.prism = Prism(log)

        self.prov = prov
        self.meta = meta
        self.cutter = Cutter(config, log)

        # ---------------------------
        # Validation Schemas (external files)
        # ---------------------------
        self.WF_SEARCH_JSON_SCHEMA = self.config.get("WF_SEARCH_JSON_SCHEMA", "schema/json/wf-search-input.schema.json")
        self.WF_SEARCH_SHACL = self.config.get("WF_SEARCH_SHACL" ,"schema/shacl/wf-search-input.shacl.ttl")
        self.WF_SELECT_JSON_SCHEMA = self.config.get("WF_SELECT_JSON_SCHEMA", "schema/json/wf-select-input.schema.json")
        self.WF_SELECT_SHACL = self.config.get("WF_SELECT_SHACL","schema/shacl/wf-select-input.shacl.ttl")
        self.WF_MANIFEST_JSON_SCHEMA = self.config.get("WF_MANIFEST_JSON_SCHEMA","schema/json/wf-manifest-output.schema.json")
        self.WF_MANIFEST_SHACL = self.config.get("WF_MANIFEST_SHACL", "schema/shacl/wf-manifest-output.shacl.ttl")


    async def get(self, prefix, handle_dirty):
        """
        URI: /resolver/<prefix>/<pid>?urlappend=metadata|provenance|document|latest|version=<n>|wf-search|wf-select
        """
        # Handler initialize

        pid = handle_dirty.split('?')[0]
        handle = f"{prefix}/{pid}"
        # request_type = self.get_query_argument("q", default="latest")
        request_type = self.get_query_argument("q", None)

        # print(f" handle_dirty  {handle_dirty}")

        if not request_type:
            urlappend = self.get_query_argument("urlappend", None)
            if urlappend and urlappend.startswith("?q="):
                request_type = urlappend[3:]

        if not request_type:
            request_type = "latest"


        self.log.info(f"Resolving PID: {handle} (request: {request_type})")

        self.log.info(
            f"Request received | prefix={prefix} pid={pid} urlappend={request_type} "
            f"query={self.request.query}"
        )

        #
        # PRISM
        #
        try:
            self.log.info(f"Invoke Prism Representation for PID: {handle} (with this request: {request_type})")
            await self.prism.execute(
                handler=self,
                pid=pid,
                handle=handle,
                request_type=request_type
            )

        except Exception as e:
            self.log.error(
                f"Error processing PID {handle}: {e}",
                exc_info=True
            )

            self.set_status(500)
            self.write({"error": "Internal server error"})




# ---------------------------
# OAI-PMH Harvester Handler
# ---------------------------
class OAIHandler(tornado.web.RequestHandler):

    def initialize(self, config, log, meta, prov):
        self.config = config
        self.log = log
        self.meta = meta
        self.prov = prov
        self.PAGE_SIZE = 10  # numero record per pagina/resumptionToken

    def get(self):
        verb = self.get_argument("verb")
        #print(f"DEBUG: verb={verb}")

        if verb == "Identify":
            #print("DEBUG: Identify")
            self.write(self.identify())

        elif verb == "ListMetadataFormats":
            #print("DEBUG: ListMetadataFormats")
            self.write(self.list_metadata_formats())

        elif verb == "ListIdentifiers":
            #print("DEBUG: ListIdentifiers")
            token = self.get_argument("resumptionToken", None)
            self.write(self.list_identifiers(resumptionToken=token))

        elif verb == "ListRecords":
            #print("DEBUG: ListRecords")
            token = self.get_argument("resumptionToken", None)
            self.write(self.list_records(resumptionToken=token))

        elif verb == "GetRecord":
            identifier = self.get_argument("identifier")
            self.write(self.get_record(identifier))

        else:
            #print("DEBUG: badVerb")
            self.write("<error>badVerb</error>")

    # ---------------------------
    # Identify
    # ---------------------------
    def identify(self):
        xml = f"""
        <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
          <Identify>
            <repositoryName>INGV EIDA NODE</repositoryName>
            <baseURL>https://repo.data.ingv.it/oai</baseURL>
            <protocolVersion>2.0</protocolVersion>
            <adminEmail>adaisacd.ont@ingv.it</adminEmail>
            <earliestDatestamp>2024-01-01</earliestDatestamp>
            <deletedRecord>no</deletedRecord>
            <granularity>YYYY-MM-DD</granularity>
            <description>
              <text>
                INGV EIDA NODE (via INGV PID-LAND) provides access to FAIR Digital Objects (FDOs) generated via RULE MANAGER (INGV RUM).
                Each PID can be resolved to retrieve multiple representations:
                
                - Resolving a PID without any urlappend parameter returns the latest version of the digital object.
                - Metadata (WF-Handle JSON-LD): append '?urlappend=?q=metadata'  
                - Provenance (WF-Provenance JSON-LD): append '?urlappend=?q=provenance'  
                - Human-readable document: append '?urlappend=?q=document'  
                - Specific version: append '?urlappend=?q=version=0'  
        
                Example: https://hdl.handle.net/11099/be9b7af6-f71f-11ee-aae9-0242ac120004?urlappend=?q=metadata
              </text>
            </description>
          </Identify>
        </OAI-PMH>
        """
        return xml.strip()

    # ---------------------------
    # ListMetadataFormats
    # ---------------------------
    def list_metadata_formats(self):
        xml = f"""
        <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
                 xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                 xmlns:dc="http://purl.org/dc/elements/1.1/">
          <ListMetadataFormats>
            <metadataFormat>
              <metadataPrefix>oai_dc</metadataPrefix>
              <schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>
              <metadataNamespace>http://www.openarchives.org/OAI/2.0/oai_dc/</metadataNamespace>
            </metadataFormat>
          </ListMetadataFormats>
        </OAI-PMH>
        """
        return xml.strip()

    # ---------------------------
    # ListIdentifiers with resumptionToken
    # ---------------------------
    def list_identifiers(self, resumptionToken=None):
        #print("DEBUG: entering list_identifiers")
        query = {"enabled": 1}
        skip = 0

        if resumptionToken:
            try:
                skip = int(resumptionToken)
            except ValueError:
                skip = 0

        cursor = self.meta.db.wf_do.find(query).sort("_id", 1).skip(skip).limit(self.PAGE_SIZE)
        records = list(cursor)
        #print(f"DEBUG: found {len(records)} records, skip={skip}")

        xml = "<ListIdentifiers>"
        for r in records:
            pid = r["dc_identifier"]
            date = r.get("dc_date", None)
            datestamp = date.strftime("%Y-%m-%d") if date else "2024-01-01"
            xml += f"<header><identifier>oai:ingv:{pid}</identifier><datestamp>{datestamp}</datestamp></header>"

        # resumptionToken
        next_skip = skip + self.PAGE_SIZE
        total_count = self.meta.db.wf_do.count_documents(query)
        if next_skip < total_count:
            xml += f'<resumptionToken>{next_skip}</resumptionToken>'

        xml += "</ListIdentifiers>"
        result = f"<OAI-PMH xmlns='http://www.openarchives.org/OAI/2.0/'>{xml}</OAI-PMH>"
        #print("DEBUG: returning XML")
        return result

    # ---------------------------
    # ListRecords with resumptionToken
    # ---------------------------
    def list_records(self, resumptionToken=None):
        #print("DEBUG: entering list_records")
        query = {"enabled": 1}
        skip = 0

        if resumptionToken:
            try:
                skip = int(resumptionToken)
            except ValueError:
                skip = 0

        cursor = self.meta.db.wf_do.find(query).sort("_id", 1).skip(skip).limit(self.PAGE_SIZE)
        records = list(cursor)
        #print(f"DEBUG: found {len(records)} records, skip={skip}")

        xml = "<ListRecords>"
        for r in records:
            xml += self.build_record(r)

        next_skip = skip + self.PAGE_SIZE
        total_count = self.meta.db.wf_do.count_documents(query)
        if next_skip < total_count:
            xml += f'<resumptionToken>{next_skip}</resumptionToken>'

        xml += "</ListRecords>"
        result = f"<OAI-PMH xmlns='http://www.openarchives.org/OAI/2.0/'>{xml}</OAI-PMH>"
        #print("DEBUG: returning XML")
        return result

    # ---------------------------
    # GetRecord
    # ---------------------------
    def get_record(self, identifier):
        pid = identifier.split(":")[-1]

        doc = self.meta.do_metadata(pid)
        if not doc:
            return "<error>idDoesNotExist</error>"

        return f"<OAI-PMH xmlns='http://www.openarchives.org/OAI/2.0/'><GetRecord>{self.build_record(doc)}</GetRecord></OAI-PMH>"

    # ---------------------------
    # build_record
    # ---------------------------
    def build_record(self, doc):
        pid = doc["dc_identifier"]
        date = doc.get("dc_date")
        datestamp = date.strftime("%Y-%m-%d") if date else "2024-01-01"

        # --- temporal ---
        temporal = ""

        start = doc["dc_coverage_t_min"]
        end = doc["dc_coverage_t_max"]
        temporal = f"{start}/{end}"

        # --- spatial ---
        spatial = ""
        lat = doc["dc_coverage_x"]
        lon = doc["dc_coverage_y"]
        alt = doc["dc_coverage_z"]
        spatial = f"lat={lat} lon={lon} alt={alt}"

        # <dc:format>{doc.get("dc_format", "application/vnd.fdsn.mseed")}</dc:format>
        # <dc:type>{doc.get("dc_type", "Dataset")}</dc:type>
        # <dc:rights>{doc.get("dc_rights", "https://creativecommons.org/publicdomain/zero/1.0/")}</dc:rights>
        return f"""
        <record>
          <header>
            <identifier>oai:ingv:{pid}</identifier>
            <datestamp>{datestamp}</datestamp>
          </header>
          <metadata>
            <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>{doc.get("dc_title", "INGV mSEED Repository")}</dc:title>
              <dc:creator>{doc.get("dc_creator", "INGV")}</dc:creator>
              <dc:publisher>{doc.get("dc_publisher", "EIDA ITALIA")}</dc:publisher>
              <dc:contributor>{doc.get("dc_contributor", "INGV")}</dc:contributor>
              <dc:subject>{doc.get("dc_subject", "seismic waveform")}</dc:subject>
              <dc:description>{doc.get("dc_description", "Seismic waveform data managed as FAIR Digital Objects")}</dc:description>
              <dc:date>{datestamp}</dc:date>
              <dc:identifier>https://hdl.handle.net/{pid}</dc:identifier>
              <dc:format>application/vnd.fdsn.mseed</dc:format>
              <dc:type>Dataset</dc:type>
              <dc:rights>https://creativecommons.org/publicdomain/zero/1.0/</dc:rights>
              <!-- version -->
              <dc:relation>version:{doc.get("dc_hasVersion", "0")}</dc:relation>
              <!-- metadata -->
              <dc:relation>
                https://hdl.handle.net/{pid}?urlappend=?q=metadata
              </dc:relation>
              <!-- provenance & versions -->
              <dc:relation>
                https://hdl.handle.net/{pid}?urlappend=?q=provenance
              </dc:relation>
              <!-- documentation -->
              <dc:relation>
                https://hdl.handle.net/{pid}?urlappend=?q=document
              </dc:relation>
              <!-- temporal coverage -->
              <dc:coverage>{temporal}</dc:coverage>
              <!-- spatial coverage -->
              <dc:coverage>{spatial}</dc:coverage>
            </oai_dc:dc>
          </metadata>
        </record>
        """


# ---------------------------
# Make Tornado App
# ---------------------------
def make_app():
    config = load_config()
    log = setup_logger(config)
    prov = Provenance(config, log)
    meta = Metadata(config, log)

    # NO (r"/resolver/(?P<prefix>\d+)/(?P<handle_dirty>[a-f0-9\-_.]+)", ResolvePIDHandler,
    return tornado.web.Application([
        (r"/oai", OAIHandler,
         {"config": config, "log": log, "meta": meta, "prov": prov }),
        (r"/(?P<prefix>\d+)/(?P<handle_dirty>.+)", ResolvePIDHandler,
         {"config": config, "log": log, "prov": prov, "meta": meta}),
    ])

# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    print("START Pid_Land")
    app = make_app()
    app.listen(8888)  # replace with config.get("HTTP_PORT", 8888)
    tornado.ioloop.IOLoop.current().start()
