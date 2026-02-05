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

# Copyright: 2025 Massimo Fares, INGV - Italy <massimo.fares@ingv.it>; EIDA Italia Team, INGV - Italy  <adaisacd.ont@ingv.it>
# License: GPLv3
# Platform: Linux
# Author: Massimo Fares, INGV - Italy <massimo.fares@ingv.it>
"""
import os
import json
import math
from pymongo import MongoClient
from datetime import datetime, timezone
from jsonschema import validate, ValidationError, Draft202012Validator
from pyshacl import validate as shacl_validate_engine
from rdflib import Graph



class Metadata:

    def __init__(self, config, log):
        self.config = config
        self.log = log

        # ---------------------------
        # Validation Schemas (external files)
        # ---------------------------
        self.WF_SEARCH_JSON_SCHEMA = self.config.get("WF_SEARCH_JSON_SCHEMA", "schema/json/wf-search-input.schema.json")
        self.WF_SEARCH_SHACL = self.config.get("WF_SEARCH_SHACL", "schema/shacl/wf-search-input.shacl.ttl")
        self.WF_SELECT_JSON_SCHEMA = self.config.get("WF_SELECT_JSON_SCHEMA", "schema/json/wf-select-input.schema.json")
        self.WF_SELECT_SHACL = self.config.get("WF_SELECT_SHACL", "schema/shacl/wf-select-input.shacl.ttl")
        self.WF_MANIFEST_JSON_SCHEMA = self.config.get("WF_MANIFEST_JSON_SCHEMA",
                                                       "schema/json/wf-manifest-output.schema.json")
        self.WF_MANIFEST_SHACL = self.config.get("WF_MANIFEST_SHACL", "schema/shacl/wf-manifest-output.shacl.ttl")

        # Mongo
        try:
            self.client = MongoClient(config["MONGO"]["HOST"], config["MONGO"]["PORT"])
            self.db = self.client[config['METADATA']['DB_NAME']]
            if config['MONGO']['AUTHENTICATE']:
                self.db.authenticate(
                    config['MONGO']['USER'],
                    config['MONGO']['PASSWORD']
                )
        except Exception:
            self.log.error("MongoDB connection failed", exc_info=True)
            raise

        # Load WF Handle JSON Schema (local, once)
        try:
            schema_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "schema", "json", "wf-handle.schema.json")
            )
            with open(schema_path, "r") as f:
                self.schema = json.load(f)
        except Exception:
            self.log.error("Failed to load WF Handle JSON Schema", exc_info=True)
            raise

    # ----------------------------
    # Find Metadata from PID
    # ----------------------------
    def do_metadata(self, handle):
        return self.db.wf_do.find_one({'dc_identifier': handle})

    # ----------------------------
    # get list of PID from bounding-box time-window
    # ----------------------------
    def do_search(self, params):
        deg_lat = params['rad'] / 111
        deg_lon = params['rad'] / (111 * math.cos(math.radians(params['lat'])))
        query = {
            "dc_coverage_t_max": {"$gte": params['start']},
            "dc_coverage_t_min": {"$lte": params['end']},
            "dc_coverage_x": {"$gte": params['lat'] - deg_lat, "$lte": params['lat'] + deg_lat},
            "dc_coverage_y": {"$gte": params['lon'] - deg_lon, "$lte": params['lon'] + deg_lon}
        }
        return list(self.db.wf_do.find(query))

    # ----------------------------
    # Find PID(s) from NSCL
    # ----------------------------
    def find_dc_identifiers(self, net, sta, loc, cha, start_time, end_time):

        loc_part = loc if loc is not None else ""

        if cha == "*":
            cha_part = r"[A-Z0-9]{3}"
        else:
            cha_part = cha

        regex = (
            f"^{net}\\.{sta}\\."
            f"{loc_part}\\."
            f"{cha_part}\\."
        )

        query = {
            "fileId": {"$regex": regex},
            "dc_coverage_t_min": {"$lte": end_time},
            "dc_coverage_t_max": {"$gte": start_time},
            "enabled": 1
        }

        projection = {"dc_identifier": 1, "_id": 0}
        results = self.db.wf_do.find(query, projection)

        return [doc["dc_identifier"] for doc in results]

    # ----------------------------
    # Convert Mongo doc to WF Handle JSON
    # ----------------------------
    def convert_to_wf_handle(self, doc):

        # "$schema": self.schema.get("$id"),
        #    "$schema": self.schema.get("$schema"),

        wf_handle = {
            "@context": {
                "dc": "http://purl.org/dc/elements/1.1/",
                "dcterms": "http://purl.org/dc/terms/",
                "schema": "http://schema.org/",
                "file": "http://schema.org/DigitalDocument"
            },
            "@type": "WF Handle",

            "dc:identifier": doc.get("dc_identifier"),
            "dc:creator": doc.get("dc_creator"),
            "dc:date": self._fmt_date(doc.get("dc_date", ''), "dc:date"),
            "dc:format": doc.get("dc_format"),
            "dc:publisher": doc.get("dc_publisher"),
            "dc:rights": doc.get("dc_rights"),
            "dc:subject": doc.get("dc_subject", ""),
            "dc:title": doc.get("dc_title"),
            # get better type
            "dc:type": f"Dataset, {doc.get('dc_type', '')}",
            "dc:hasVersion": doc.get("dc_hasVersion", "0"),

            "dc:description": (
                f"Detailed documentation available at "
                f"http://hdl.handle.net/{doc.get('dc_identifier')}?urlappend=document"
            ),
            "dc:provenance": (
                f"Provenance information available at "
                f"http://hdl.handle.net/{doc.get('dc_identifier')}?urlappend=provenance"
            ),

            "dcterms:temporal": {
                "dcterms:start": self._fmt_date(doc.get("dc_coverage_t_min"), "dcterms:start"),
                "dcterms:end": self._fmt_date(doc.get("dc_coverage_t_max"), "dcterms:end")
            },

            "dcterms:spatial": {
                "schema:latitude": doc.get("dc_coverage_x"),
                "schema:longitude": doc.get("dc_coverage_y"),
                "schema:altitude": doc.get("dc_coverage_z", 0)
            },

            "dcterms:available": self._fmt_date(doc.get("dcterms_available"), "dcterms:available"),
            "dcterms:dateAccepted": self._fmt_date(doc.get("dcterms_dateAccepted"), "dcterms:dateAccepted"),
            "dcterms:isPartOf": doc.get("dcterms_isPartOf"),

            "file": {
                "schema:name": doc.get("fileId"),
                "schema:url": f"http://hdl.handle.net/{doc.get('dc_identifier')}"
            }
        }

        # JSON Schema validation (structure)
        self._validate(wf_handle)

        # SHACL validation (semantics)
        self._shacl_validate(wf_handle)

        return wf_handle


    # ----------------------------
    # Generate RO-Crate JSON
    # ----------------------------
    def generate_ro_crate(self, file_ids):
        """
        Generate an RO-Crate 1.1 JSON for a list of WF Handles.
        """

        ro_crate = self._init_ro_crate()

        for fid in file_ids:

            # --- PATCH: normalize PID input ---
            if isinstance(fid, dict):
                pid = fid.get("dc_identifier")
            else:
                pid = fid

            if not pid:
                self.log.warning(f"Invalid PID entry: {fid}")
                continue
            # --- END PATCH ---

            doc = self.db.wf_do.find_one({"dc_identifier": pid})
            if not doc:
                self.log.warning(f"WF Handle not found: {pid}")
                continue

            entity = self._build_ro_crate_file_entity(doc)
            ro_crate["@graph"].append(entity)
            ro_crate["@graph"][1]["hasPart"].append({"@id": entity["@id"]})

        return ro_crate

    # ----------------------------
    # Init RO-Crate JSON
    # ----------------------------
    def _init_ro_crate(self):
        return {
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": [
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"}
                },
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "name": "INGV mSEED Waveform Collection",
                    "description": "Collection of seismic waveform data",
                    "publisher": {
                        "@type": "Organization",
                        "name": "INGV EIDA NODE"
                    },
                    "hasPart": []
                }
            ]
        }

    # ----------------------------
    # Build RO-Crate JSON
    # ----------------------------
    def _build_ro_crate_file_entity(self, doc):

        dc_id = doc.get("dc_identifier")

        return {
            "@id": f"https://hdl.handle.net/{dc_id}",
            "@type": "MediaObject",
            "name": doc.get("fileId"),
            "encodingFormat": "application/vnd.fdsn.mseed",

            "temporalCoverage": {
                "@type": "PeriodOfTime",
                "startDate": self._fmt_date(doc.get("dc_coverage_t_min")),
                "endDate": self._fmt_date(doc.get("dc_coverage_t_max"))
            },

            "spatialCoverage": {
                "@type": "Place",
                "geo": {
                    "@type": "GeoCoordinates",
                    "latitude": doc.get("dc_coverage_x"),
                    "longitude": doc.get("dc_coverage_y"),
                    "elevation": doc.get("dc_coverage_z", 0)
                }
            },

            "license": doc.get("dc_rights"),

            "provenance": (
                f"http://hdl.handle.net/{dc_id}?urlappend=provenance"
            ),
            "metadata": (
                f"http://hdl.handle.net/{dc_id}?urlappend=metadata"
            )
        }

    # ----------------------------
    # Check date format
    # ----------------------------
    def _fmt_date(self, dt, field_name=None):
        """
        Format a date value to ISO 8601 (UTC, Z).

        Accepts:
        - datetime.datetime
        - ISO 8601 string
        - MongoDB {"$date": "..."}
        """

        if not dt:
            return None

        original = dt

        # Mongo extended JSON
        if isinstance(dt, dict) and "$date" in dt:
            dt = dt["$date"]

        # Native datetime from Mongo
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        # ISO string
        if isinstance(dt, str):
            try:
                return datetime.fromisoformat(dt.rstrip("Z")).isoformat() + "Z"
            except Exception as e:
                self.log.warning(
                    f"Could not parse date for {field_name}: '{original}' ({e})"
                )
                return None

        # Anything else → warning
        self.log.warning(
            f"Invalid date type for {field_name}: "
            f"{type(original).__name__} ({original})"
        )
        return None

    # ----------------------------
    # Schema Validator
    # ----------------------------
    def _validate(self, data):
        try:
            Draft202012Validator(self.schema).validate(data)
        except ValidationError as e:
            self.log.error(
                "WF Handle validation failed",
                extra={"error": str(e), "instance": data}
            )
            raise

    # ----------------------------
    # SHACL Validator (JSON-LD)
    # ----------------------------
    def _shacl_validate(self, jsonld_data):
        """
        Validate WF Handle against SHACL constraints.
        """

        shacl_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "schema",
                "shacl",
                "wf-handle.shacl.ttl"
            )
        )

        try:
            data_graph = Graph().parse(
                data=json.dumps(jsonld_data),
                format="json-ld"
            )

            shacl_graph = Graph().parse(
                shacl_path,
                format="turtle"
            )

            conforms, report_graph, report_text = shacl_validate_engine(
                data_graph,
                shacl_graph=shacl_graph,
                inference="rdfs",
                abort_on_first=False,
                allow_infos=False,
                allow_warnings=False
            )

            if not conforms:
                self.log.error("SHACL validation failed")
                self.log.error(report_text)
                raise ValueError("WF Handle SHACL validation failed")

        except Exception:
            self.log.error("SHACL validation error", exc_info=True)
            raise
