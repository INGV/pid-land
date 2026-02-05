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
from pymongo import MongoClient
from jsonschema import Draft202012Validator, ValidationError
from datetime import datetime, timezone

class Provenance:
    def __init__(self, config, log):
        self.config = config
        self.log = log



        # MongoDB connection
        try:
            self.client = MongoClient(config["MONGO"]["HOST"], config["MONGO"]["PORT"])
            self.db = self.client[config['PROVENANCE']['DB_NAME']]
            if config['MONGO'].get('AUTHENTICATE', False):
                self.db.authenticate(
                    config['MONGO']['USER'],
                    config['MONGO']['PASSWORD']
                )
        except Exception:
            self.log.error("MongoDB connection failed", exc_info=True)
            raise

        # Load WF Provenance JSON Schema
        try:
            schema_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "schema", "json", "wf-provenance.schema.json")
            )
            with open(schema_path, "r") as f:
                self.schema = json.load(f)
        except Exception:
            self.log.error("Failed to load WF Provenance JSON Schema", exc_info=True)
            raise

    # ----------------------------
    # Retrieve provenance & revisions for a handle
    # ----------------------------
    def get_provenance(self, handle):
        doc = self.db.do_prov.find_one({"dc_identifier": handle})
        revisions = list(self.db.do_vers.find({"dc_identifier": handle}).sort("dc_hasVersion", 1))
        doc['prov_wasRevisionOf'] = revisions
        return doc

    # ----------------------------
    # Retrieve specific version
    # ----------------------------
    def get_version(self, handle, version):
        return self.db.do_vers.find_one({"dc_identifier": handle, "dc_hasVersion": version})

    # ----------------------------
    # Convert Mongo doc to WF Provenance JSON
    # ----------------------------
    def convert_to_wf_provenance(self, doc):

        #  "$schema": self.schema.get("$id"),

        wf_prov = {
            "@context": {
                "dc": "http://purl.org/dc/elements/1.1/",
                "dcterms": "http://purl.org/dc/terms/",
                "prov": "http://www.w3.org/ns/prov#",
                "schema": "http://schema.org/"
            },
            "@type": "WF Provenance",
            "dc:identifier": doc.get("dc_identifier"),
            "dcterms:isPartOf": "wf_handle",
            "prov:generatedAtTime": self._fmt_date(doc.get("prov_generatedAtTime")),
            "prov:wasAttributedTo": doc.get("prov_wasAttributedTo", ""),
            "prov:usage": self._safe_usage(doc.get("prov_usage")),
            "prov:wasRevisionOf": []
        }

        # Add revisions
        for rev in doc.get('prov_wasRevisionOf', []):
            try:
                revision_data = {
                    "dc:hasVersion": self._safe_int(rev.get('dc_hasVersion', 0)),
                    "schema:startDate": self._fmt_date(rev.get('schema_startDate')),
                    "schema:Organization": rev.get('schema_Organization', ""),
                    "prov:SoftwareAgent": self._safe_uri_array(rev.get('prov_SoftwareAgent', [])),
                    "dcterms:spatial": self._safe_spatial(rev.get('dc_terms_spatial', {})),
                    "schema:file": self._safe_file(rev.get('schema_file', {})),
                    "prov:wasGeneratedBy": self._safe_generated_by(rev.get('prov_wasGeneratedBy', {}))
                }
                wf_prov["prov:wasRevisionOf"].append(revision_data)
            except Exception as e:
                self.log.warning(f"Skipping invalid revision for {doc.get('dc_identifier')}: {e}")

        self._validate(wf_prov)
        return wf_prov

    # ----------------------------
    # Schema Validator
    # ----------------------------
    def _validate(self, data):
        try:
            Draft202012Validator(self.schema).validate(data)
        except ValidationError as e:
            self.log.error(
                "WF Provenance validation failed",
                extra={"error": str(e), "instance": data}
            )
            raise

    # ----------------------------
    # Helper: format date
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
    # Helper: ensure integer
    # ----------------------------
    def _safe_int(self, val):
        try:
            return int(val)
        except Exception:
            return 0

    # ----------------------------
    # Helper: ensure array of URI strings
    # ----------------------------
    def _safe_uri_array(self, val):
        if not isinstance(val, list):
            return []
        return [str(v) for v in val]

    # ----------------------------
    # Helper: spatial object
    # ----------------------------
    def _safe_spatial(self, val):
        return {
            "x": float(val.get("x", 0)),
            "y": float(val.get("y", 0)),
            "z": float(val.get("z", 0))
        }

    # ----------------------------
    # Helper: schema:file object
    # ----------------------------
    def _safe_file(self, val):
        return {
            "name": val.get("name", ""),
            "position": val.get("position", "")
        }

    # ----------------------------
    # Helper: prov:wasGeneratedBy object
    # ----------------------------
    def _safe_generated_by(self, val):
        return {
            "prov:hadPrimarySource": val.get("prov_hadPrimarySource", ""),
            "schema:SoftwareApplication": self._safe_uri_array(val.get("schema_SoftwareApplication", [])),
            "schema:Organization": val.get("schema_Organization", ""),
            "dcterms:accrualPeriodicity": val.get("dcterms_accrualPeriodicity", "")
        }

    # ----------------------------
    # Helper: prov:usage
    # ----------------------------
    def _safe_usage(self, val):
        if not isinstance(val, dict):
            return {"schema:SoftwareApplication": []}
        return {
            "schema:SoftwareApplication": self._safe_uri_array(val.get("schema:SoftwareApplication", []))
        }
