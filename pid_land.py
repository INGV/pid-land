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
from pathlib import Path
import yaml
import logging
from logging.handlers import TimedRotatingFileHandler
import tornado.ioloop
import tornado.web
import json
from jsonschema import validate, ValidationError
from pyshacl import validate as shacl_validate
from rdflib import Graph
import re
from modules.provenance import Provenance
from modules.metadata import Metadata

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
        self.prov = prov
        self.meta = meta

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
        request_type = self.get_query_argument("urlappend", default="latest")
        # print(f" dirty: {handle_dirty} - pid: {pid} request: {request_type}")

        self.log.info(f"Resolving PID: {handle} (request: {request_type})")

        self.log.info(
            f"Request received | prefix={prefix} pid={pid} urlappend={request_type} "
            f"query={self.request.query}"
        )

        try:
            # pid
            if request_type.startswith("version="):
                version = request_type.split("=")[1]
                await self._send_version(handle, version)
            elif request_type == "provenance":
                await self._send_provenance(handle)
            elif request_type == "metadata":
                await self._send_metadata(handle)
            elif request_type == "document":
                await self._send_document()
            # special pids
            elif pid == "wf-search":
                await self._send_wf_search(request_type)
            elif pid == "wf-select":
                await self._send_wf_select(request_type)
            # latest
            elif request_type == "latest":
                await self._send_latest(handle)
            else:
                self.set_status(404)
                self.write({"error": "Malformed request"})
                return

        except Exception as e:
            self.log.error(f"Error processing PID {handle}: {e}", exc_info=True)
            self.set_status(500)
            self.write({"error": "Internal server error"})

    # ---------------------------
    # Internal Handlers
    # ---------------------------
    async def _send_version(self, handle, version):
        doc = self.prov.get_version(handle, version)
        if not doc:
            self.set_status(404)
            self.write({"error": "Version not found"})
            return

        file_name = doc.get("schema_file", {}).get("name") or doc.get("fileId")
        if not file_name:
            self.set_status(404)
            self.write({"error": "No file reference in version document"})
            return

        await self._stream_file(file_name, archive="VERS_ARCHIVE")

    async def _send_latest(self, handle):
        doc = self.meta.do_metadata(handle)
        if not doc:
            self.set_status(404)
            self.write({"error": "PID not found"})
            return
        await self._stream_file(doc['fileId'], archive="PROD_ARCHIVE")

    async def _send_provenance(self, handle):
        prov_doc = self.prov.get_provenance(handle)
        self.set_header("Content-Type", "application/ld+json")
        self.write(self.prov.convert_to_wf_provenance(prov_doc))

    async def _send_metadata(self, handle):
        meta_doc = self.meta.do_metadata(handle)
        self.set_header("Content-Type", "application/ld+json")
        self.write(self.meta.convert_to_wf_handle(meta_doc))

    async def _send_document(self):
        message_default = (
            "The International Federation of Digital Seismograph Networks (FDSN) defines miniSEED "
            "as a format for digital data and related information. Metadata counterpart: StationXML."
        )
        message = self.config.get("MESSAGE_DOCUMENT", message_default)
        self.write({"message": message})

    # ---------------------------
    # Validation helpers
    # ---------------------------

    # ---------------------------
    # WF-Search JSON Schema Validation
    # ---------------------------
    def _validate_wf_search_json(self, data):
        try:
            with open(self.WF_SEARCH_JSON_SCHEMA, "r") as f:
                schema = json.load(f)
            validate(instance=data, schema=schema)
        except FileNotFoundError:
            self.log.error("WF search JSON schema not found")
            self.set_status(500)
            self.write({"error": "Validation schema missing"})
            return False
        except ValidationError as e:
            self.set_status(400)
            self.write({
                "error": "Invalid wf-search input (JSON Schema)",
                "details": e.message
            })
            return False
        return True

    # ---------------------------
    # WF-Search SHACL Validation
    # ---------------------------
    def _validate_wf_search_shacl(self, data):
        try:
            data_graph = Graph()
            data_graph.parse(
                data=json.dumps(data),
                format="json-ld"
            )

            shacl_graph = Graph()
            shacl_graph.parse(self.WF_SEARCH_SHACL, format="turtle")

            conforms, _, report = shacl_validate(
                data_graph=data_graph,
                shacl_graph=shacl_graph,
                inference="rdfs"
            )
        except FileNotFoundError:
            self.log.error("WF search SHACL file not found")
            self.set_status(500)
            self.write({"error": "SHACL schema missing"})
            return False

        if not conforms:
            self.set_status(422)
            self.write({
                "error": "Invalid wf-search input (SHACL)",
                "details": report
            })
            return False

        return True

    # ---------------------------
    # WF-Search send response
    # ---------------------------
    async def _send_wf_search(self, request_type):
        from datetime import datetime

        try:
            lat = self.get_query_argument("lat")
            lon = self.get_query_argument("lon")
            rad = self.get_query_argument("rad")
            start = self.get_query_argument("start")
            end = self.get_query_argument("end")

            # --- check param vuoti ---
            missing = [p for p, v in (("lat", lat), ("lon", lon), ("rad", rad), ("start", start), ("end", end)) if
                       not v]
            if missing:
                self.set_status(400)
                self.write({"error": f"Missing parameter(s) or empty value: {', '.join(missing)}"})
                return

            # --- validate numeric types ---
            try:
                lat_f = float(lat)
                lon_f = float(lon)
                rad_i = int(rad)
            except ValueError:
                self.set_status(400)
                self.write({"error": "Invalid numeric parameter type for lat/lon/rad"})
                return

            # --- check lat/lon ranges ---
            if not (-90 <= lat_f <= 90):
                self.set_status(400)
                self.write({"error": "Latitude out of range: must be between -90 and 90"})
                return
            if not (-180 <= lon_f <= 180):
                self.set_status(400)
                self.write({"error": "Longitude out of range: must be between -180 and 180"})
                return

            # --- validate date format ---
            try:
                start_dt = datetime.fromisoformat(start)
                end_dt = datetime.fromisoformat(end)
            except ValueError:
                self.set_status(400)
                self.write({"error": "Invalid date format, must be ISO 8601 (YYYY-MM-DD)"})
                return

            # --- logical check start <= end ---
            if start_dt > end_dt:
                self.set_status(400)
                self.write({"error": "Temporal logic error: start must be earlier than or equal to end"})
                return

            # --- prepare params JSON-LD ---
            params = {
                "@type": "WFSearchRequest",
                "spatial": {
                    "lat": lat_f,
                    "lon": lon_f,
                    "rad": rad_i,
                },
                "temporal": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                }
            }

        except tornado.web.MissingArgumentError as e:
            self.set_status(400)
            self.write({"error": f"Missing parameter: {e.arg_name}"})
            return

        # --- JSON Schema validation ---
        if not self._validate_wf_search_json(params):
            return

        # --- SHACL validation ---
        if not self._validate_wf_search_shacl(params):
            return

        # --- business logic unchanged ---
        flat_params = {
            **params["spatial"],
            **params["temporal"]
        }

        results = self.meta.do_search(flat_params)
        ids = [doc['dc_identifier'] for doc in results]

        #self.set_header("Content-Type", "application/ld+json")
        #self.write(self.meta.generate_ro_crate(ids))

        ro_crate = self.meta.generate_ro_crate(ids)

        # Validation RO-Crate manifest
        if not self._validate_manifest_json(ro_crate):
            return
        if not self._validate_manifest_shacl(ro_crate):
            return

        self.log.info(
            "WF-Search manifest generated | "
            f"hasPart={len(ro_crate.get('@graph', [])[1].get('hasPart', []))}"
        )

        self.set_header("Content-Type", "application/ld+json")
        self.write(json.dumps(ro_crate, indent=2))

    # ---------------------------
    # WF-Select JSON Schema Validation
    # ---------------------------
    def _validate_wf_select_json(self, data):
        import jsonschema
        import json

        schema_path = Path(self.WF_SELECT_JSON_SCHEMA)
        if not schema_path.is_file():
            self.set_status(500)
            self.write({"error": f"WF-Select input JSON Schema not found at {schema_path}"})
            return False

        with open(schema_path, "r") as f:
            schema = json.load(f)

        try:
            jsonschema.validate(instance=data, schema=schema)
            return True
        except jsonschema.ValidationError as e:
            self.set_status(400)
            self.write({"error": f"WF-Select JSON Schema validation error: {e.message}"})
            return False

    # ---------------------------
    # WF-Select SHACL Validation
    # ---------------------------
    def _validate_wf_select_shacl(self, data):
        from pyshacl import validate
        import rdflib

        shacl_path = Path(self.WF_SELECT_SHACL)
        if not shacl_path.is_file():
            self.set_status(500)
            self.write({"error": f"WF-Select input SHACL not found at {shacl_path}"})
            return False

        g_data = rdflib.Graph()
        g_data.parse(data=json.dumps(data), format="json-ld")

        conforms, results_graph, results_text = validate(
            data_graph=g_data,
            shacl_graph=str(shacl_path),
            ont_graph=None,
            inference='rdfs',
            abort_on_first=False,
            meta_shacl=False,
            debug=False
        )

        if not conforms:
            self.set_status(400)
            self.write({"error": "WF-Select SHACL validation failed", "details": results_text})
            return False

        return True

    # ---------------------------
    # WF-Manifest JSON Schema Validation
    # ---------------------------
    def _validate_manifest_json(self, data):
        import json
        from jsonschema import validate, ValidationError

        try:
            with open(self.WF_MANIFEST_JSON_SCHEMA, "r") as f:
                schema = json.load(f)
            validate(instance=data, schema=schema)
        except FileNotFoundError:
            self.log.error(f"WF-Manifest JSON schema not found: {self.WF_MANIFEST_JSON_SCHEMA}")
            self.set_status(500)
            self.write({"error": "Manifest validation schema missing"})
            return False
        except ValidationError as e:
            self.set_status(400)
            self.write({
                "error": "WF-Manifest JSON Schema validation failed",
                "details": e.message
            })
            return False

        self.log.info("WF-Manifest JSON Schema validation passed")
        return True

    # ---------------------------
    # WF-Manifest SHACL Validation
    # ---------------------------
    def _validate_manifest_shacl(self, data):
        import json
        from rdflib import Graph
        from pyshacl import validate as shacl_validate

        try:
            g_data = Graph()
            g_data.parse(data=json.dumps(data), format="json-ld")

            shacl_graph = Graph()
            shacl_graph.parse(self.WF_MANIFEST_SHACL, format="turtle")

            conforms, _, report = shacl_validate(
                data_graph=g_data,
                shacl_graph=shacl_graph,
                inference="rdfs"
            )

        except FileNotFoundError:
            self.log.error(f"WF-Manifest SHACL file not found: {self.WF_MANIFEST_SHACL}")
            self.set_status(500)
            self.write({"error": "Manifest SHACL schema missing"})
            return False

        if not conforms:
            self.set_status(422)
            self.write({"error": "WF-Manifest SHACL validation failed", "details": report})
            return False

        self.log.info("WF-Manifest SHACL validation passed")
        return True

    # ---------------------------
    # WF-Select send response
    # ---------------------------
    async def _send_wf_select(self, request_type):
        from datetime import datetime

        try:
            net = self.get_query_argument("net")
            sta = self.get_query_argument("sta")
            loc = self.get_query_argument("loc", default=None)
            cha = self.get_query_argument("cha")
            start = self.get_query_argument("start")
            end = self.get_query_argument("end")

            # --- wildcard policy ---
            if net == "*" or sta == "*":
                self.set_status(413)
                self.write({
                    "error": "Query too large",
                    "details": "Wildcard '*' is not allowed for network or station"
                })
                return

            # --- check empty param ---
            missing = [p for p, v in (("net", net), ("sta", sta), ("cha", cha),
                                      ("start", start), ("end", end)) if not v]

            if missing:
                self.set_status(400)
                self.write({"error": f"Missing parameter(s) or empty value: {', '.join(missing)}"})
                return
            if loc == "":
                loc = None

            self.log.info(
                "WF-Select normalized parameters | "
                f"net={net} sta={sta} loc={loc} cha={cha} "
                f"start={start} end={end}"
            )

            if loc is None:
                self.log.warning("WF-Select request without location code (loc=None)")

            if cha == "*":
                self.log.info(
                    "WF-Select wildcard channel query | "
                    f"net={net} sta={sta} loc={loc or '--'} "
                    f"start={start} end={end}"
                )

            # --- validate network/station/channel ---
            network_pattern = r"^[A-Z0-9]{2}$"
            station_pattern = r"^[A-Z0-9]{4,5}$"
            channel_pattern = r"^(B[HL][ZEN]|HH[ZEN]|EH[ZEN]|LH[ZEN]|VM[EN]|HN[ZEN]|MDI|LKI)$"

            if not re.match(network_pattern, net):
                self.set_status(400)
                self.write({"error": f"Invalid network code: {net}. Must be 2 chars (letters or digits)."})
                return

            if not re.match(station_pattern, sta):
                self.set_status(400)
                self.write({"error": f"Invalid station code: {sta}. Must be 4 or 5 chars (letters or digits)."})
                return

            if cha != "*" and not re.match(channel_pattern, cha):
                self.set_status(400)
                self.write({
                    "error": f"Invalid channel code: {cha}. Must be one of BHZ/BHN/... or '*'"
                })
                return

            # --- validate date format ---
            try:
                start_dt = datetime.fromisoformat(start)
                end_dt = datetime.fromisoformat(end)
            except ValueError:
                self.set_status(400)
                self.write({"error": "Invalid date format, must be ISO 8601 (YYYY-MM-DD)"})
                return

            # --- logical check start <= end ---
            if start_dt > end_dt:
                self.set_status(400)
                self.write({"error": "Temporal logic error: start must be earlier than or equal to end"})
                return

            # --- prepare params JSON-LD ---
            params = {
                "@type": "WFSelectRequest",
                "network": net,
                "station": sta,
                "location": loc,
                "channel": cha,
                "temporal": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                }
            }

        except tornado.web.MissingArgumentError as e:
            self.set_status(400)
            self.write({"error": f"Missing parameter: {e.arg_name}"})
            return

        # --- JSON Schema validation ---
        if not self._validate_wf_select_json(params):
            return
        self.log.info("WF-Select JSON Schema validation: OK")

        # --- SHACL validation ---
        if not self._validate_wf_select_shacl(params):
            return
        self.log.info("WF-Select SHACL validation: OK")

        self.log.info(
            "WF-Select executing backend query | "
            f"net={params['network']} sta={params['station']} "
            f"loc={params['location']} cha={params['channel']} "
            f"start={params['temporal']['start']} end={params['temporal']['end']}"
        )

        # --- business logic unchanged ---
        ids = self.meta.find_dc_identifiers(
            params['network'], params['station'], params['location'], params['channel'],
            params['temporal']['start'], params['temporal']['end']
        )

        self.log.info(f"WF-Select backend returned {len(ids)} identifiers")

        if not ids:
            self.log.warning(
                "WF-Select empty result set | "
                f"net={params['network']} sta={params['station']} "
                f"loc={params['location']} cha={params['channel']} "
                f"start={params['temporal']['start']} end={params['temporal']['end']}"
            )


        ro_crate = self.meta.generate_ro_crate(ids)

        # Validation RO-Crate manifest
        if not self._validate_manifest_json(ro_crate):
            return
        if not self._validate_manifest_shacl(ro_crate):
            return

        self.log.info(
            "WF-Select manifest generated | "
            f"hasPart={len(ro_crate.get('@graph', [])[1].get('hasPart', []))}"
        )

        self.set_header("Content-Type", "application/ld+json")
        self.write(json.dumps(ro_crate, indent=2))

    # ---------------------------
    # RO-Crate output JSON Schema Validation
    # ---------------------------
    def _validate_ro_crate_json(self, ro_crate_str):
        import json
        import jsonschema

        try:
            ro_crate = json.loads(ro_crate_str)
        except json.JSONDecodeError as e:
            self.log.error(f"RO-Crate JSON decode error: {e}")
            self.set_status(500)
            self.write({"error": "Invalid RO-Crate JSON"})
            return False

        try:
            with open(self.WF_MANIFEST_JSON_SCHEMA) as f:
                schema = json.load(f)
            jsonschema.validate(instance=ro_crate, schema=schema)
        except FileNotFoundError:
            self.log.error("RO-Crate output JSON Schema not found")
            self.set_status(500)
            self.write({"error": "RO-Crate output JSON Schema missing"})
            return False
        except jsonschema.ValidationError as e:
            self.log.error(f"RO-Crate JSON Schema validation failed: {e.message}")
            self.set_status(500)
            self.write({"error": "RO-Crate output JSON Schema validation failed", "details": e.message})
            return False

        self.log.info("RO-Crate JSON Schema validation passed")
        return True

    # ---------------------------
    # RO-Crate output SHACL Validation
    # ---------------------------
    def _validate_ro_crate_shacl(self, ro_crate_str):
        from rdflib import Graph
        from pyshacl import validate
        import json

        try:
            g_data = Graph()
            g_data.parse(data=ro_crate_str, format="json-ld")

            shacl_path = self.WF_MANIFEST_SHACL
            g_shacl = Graph()
            g_shacl.parse(shacl_path, format="turtle")

            conforms, results_graph, results_text = validate(
                data_graph=g_data,
                shacl_graph=g_shacl,
                inference='rdfs',
                abort_on_first=False
            )

            if not conforms:
                self.log.error(f"RO-Crate SHACL validation failed: {results_text}")
                self.set_status(500)
                self.write({"error": "RO-Crate SHACL validation failed", "details": results_text})
                return False

        except Exception as e:
            self.log.error(f"RO-Crate SHACL validation exception: {e}")
            self.set_status(500)
            self.write({"error": "RO-Crate SHACL validation exception", "details": str(e)})
            return False

        self.log.info("RO-Crate SHACL validation passed")
        return True

    # ---------------------------
    # File streaming with security
    # ---------------------------
    async def _stream_file(self, file_name, archive="PROD_ARCHIVE"):
        archive_dir = Path(self.config.get(archive, "/mnt/archive")).resolve()

        # sds file/path
        # NET.STA.LOC.CHA.TYPE.YEAR.DAY
        #  0   1   2   3    4     5    6
        parts = file_name.split(".")
        if len(parts) < 6:
            raise ValueError(f"Invalid SDS filename: {file_name}")
        year = parts[5]
        net = parts[0]
        sta = parts[1]
        cha = parts[3]
        abs_path = archive_dir / year / net / sta / f"{cha}.D" / file_name

        # sds check
        if not str(abs_path).startswith(str(archive_dir)) or not abs_path.is_file():
            self.set_status(404)
            self.write({"error": "File not found"})
            return

        #set header
        self.set_header("Content-Type", "application/octet-stream")
        self.set_header("Content-Disposition", f'attachment; filename="{abs_path.name}"')

        # go
        with open(abs_path, "rb") as f:
            while chunk := f.read(4096):
                self.write(chunk)
                await self.flush()

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
