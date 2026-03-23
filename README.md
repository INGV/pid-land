# PID-LAND

## Overview

PID-LAND is a **PID-centric resolver and landing service** designed to provide persistent, FAIR, and provenance-aware access to seismological waveform data.

At its core, PID-LAND adopts an **information-centric architecture**: a Persistent Identifier (PID) does **not** identify a file, a URL, or a backend service, but a **conceptual digital object**. This conceptual object represents the scientific meaning of the data—independent of how, where, or in which format the data are stored.

From a single PID, multiple **representations** of the same object can be resolved in a controlled and coherent way, including data, metadata, provenance records, and aggregated dataset views.

---

## Conceptual Digital Objects

In PID-LAND, a **conceptual digital object** is a logical entity that represents a waveform dataset as a scientific object, rather than as a physical file.

A conceptual digital object:

* exists independently of storage layout or delivery mechanisms
* remains stable across file migrations, format changes, or infrastructure evolution
* can be resolved into different representations depending on the user or machine request

This distinction between *what the object is* and *how it is materialized* is fundamental to long-term persistence, interoperability, and reproducibility.

> **A PID identifies the concept; representations are views of that concept.**

---

## Resolver Architecture

### Single Resolver Endpoint
PID-LAND exposes a single, stable **public resolver endpoint**:


```
https://hdl.handle.net/<prefix>/<pid>
```


The PID (`<prefix>/<pid>`) always refers to the same **conceptual digital object**. It never encodes:


- file paths
- storage locations
- backend services
- access protocols


### Public vs. Project Endpoint


While `hdl.handle.net` provides a **universal, public entry point**, all actual data and services are hosted on the project infrastructure (e.g., `https://my-resolver.net`).


The PID manager stores the mapping between the PID and the internal project URL. When a user resolves the PID via `hdl.handle.net`, the resolver performs a **redirect to the project-specific endpoint**:


```
User -> https://hdl.handle.net/<prefix>/<pid> -> PID-LAND resolver -> redirect -> https://my-resolver.net/<prefix>/<pid>
```


This approach ensures:


- The PID remains **persistent and stable**.
- The underlying storage, service, or protocol can change without breaking the PID.
- Users always access the **conceptual digital object** without needing to know internal infrastructure details.
### Information-Centric Design Rationale

Traditional data services often adopt a **system-centric** approach, where identifiers are tightly coupled to specific services, storage locations, or representations. This typically leads to:

* Different URLs for data, metadata, and provenance
* Fragmentation of identifiers
* Reduced long-term persistence and interoperability

PID-LAND deliberately follows an **information-centric approach**, 
where the PID is the stable reference and systems and services are interchangeable. 
Representations can evolve without breaking identifiers and independent of:

* Storage backends
* File paths
* Software components
* Representation formats

This design aligns with established PID infrastructures (Handle, DOI) and extends them toward **FAIR Digital Objects**.

---

## Resolver Contract and Representations

PID-LAND implements a clear **resolver contract**: different representations are obtained by specifying the requested view through the `urlappend` parameter.

| Resolution request                     | Resulting representation                      |
|----------------------------------------|-----------------------------------------------|
| `<prefix>/<pid>`                       | Default view (latest dataset state) (MSEED)   |
| `<prefix>/<pid>?urlappend=?q=metadata` | WF Handle metadata (JSON-LD)                  |
| `<prefix>/<pid>?urlappend=?q=provenance`  | WF Provenance record (JSON-LD)                |
| `<prefix>/<pid>?urlappend=?q=version=<n>` | Specific historical version  (MSEED)          |
| `<prefix>/<pid>?urlappend=?q=document`    | Human readble documentation  (TXT)       |
| `<prefix>/wf-search?urlappend=?q=...`               | Aggregated dataset (WF-Manifest, RO-Crate)    |
| `<prefix>/wf-select?urlappend=?q=...`               | Deterministic dataset (WF-Manifest, RO-Crate) |

All views are resolved from the **same identifier**, ensuring semantic coherence between data, metadata, and provenance.

---
## OAI-PMH Interface

PID-LAND exposes FAIR Digital Objects through an **OAI-PMH interface** for scalable metadata harvesting.

### Endpoint
```
http://<resolver>/oai?verb=...
```
### Supported verbs

- Identify
- ListIdentifiers
- ListRecords
- GetRecord
- ListMetadataFormats

### Key features

- **Dublin Core metadata (oai_dc)**
- **resumptionToken pagination**
- **globally resolvable identifiers (PID-based)**
- **machine-readable guidance via Identify/description**

---

## WF-Handle → OAI-PMH Mapping

OAI-PMH records are a **projection of WF-Handle metadata**, not an independent representation.

Core fields are mapped as follows:

| WF-Handle | OAI_DC |
|----------|--------|
| dc:identifier | dc:identifier |
| dc:title | dc:title |
| dc:creator | dc:creator |
| dc:publisher | dc:publisher |
| dc:subject | dc:subject |
| dc:date | dc:date |
| dc:format | dc:format |
| dc:type | dc:type |
| dc:rights | dc:rights |
| version | dc:relation |
| provenance link | dc:relation |
| document link | dc:relation |
| temporal | dc:coverage |
| spatial | dc:coverage |

### Important design note

OAI-PMH provides a **simplified, interoperable metadata view**, while full representations remain accessible via PID resolution.

Links to advanced representations are exposed through:
```
dc:relation → ?urlappend=?q=metadata
dc:relation → ?urlappend=?q=provenance
dc:relation → ?urlappend=?q=document
```

> **OAI-PMH enables discovery; PID-LAND enables full access.**

---

### Example: GetRecord

This request
```
http://<resolver>/oai?verb=GetRecord&identifier=oai:ingv:<pid>&metadataPrefix=oai_dc
```

retrieve this
```
<record>
          <header>
            <identifier>oai:ingv:11099/b89bd40c-aaf3-11ee-ad3c-0242ac120013</identifier>
            <datestamp>2024-01-04</datestamp>
          </header>
          <metadata>
            <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>INGV mSEED Repository</dc:title>
              <dc:creator>INGV ITALY</dc:creator>
              <dc:publisher>EIDA ITALIA</dc:publisher>
              <dc:contributor>network operator</dc:contributor>
              <dc:subject>mSEED, waveform, seismic data</dc:subject>
              <dc:description>Seismic waveform data managed as FAIR Digital Objects</dc:description>
              <dc:date>2024-01-04</dc:date>
              <dc:identifier>https://hdl.handle.net/11099/b89bd40c-aaf3-11ee-ad3c-0242ac120013</dc:identifier>
              <dc:format>application/vnd.fdsn.mseed</dc:format>
              <dc:type>Dataset</dc:type>
              <dc:rights>https://creativecommons.org/publicdomain/zero/1.0/</dc:rights>
              <!-- version -->
              <dc:relation>version:0</dc:relation>
              <!-- metadata -->
              <dc:relation>
                https://hdl.handle.net/11099/b89bd40c-aaf3-11ee-ad3c-0242ac120013?urlappend=?q=metadata
              </dc:relation>
              <!-- provenance & versions -->
              <dc:relation>
                https://hdl.handle.net/11099/b89bd40c-aaf3-11ee-ad3c-0242ac120013?urlappend=?q=provenance
              </dc:relation>
              <!-- documentation -->
              <dc:relation>
                https://hdl.handle.net/11099/b89bd40c-aaf3-11ee-ad3c-0242ac120013?urlappend=?q=document
              </dc:relation>
              <!-- temporal coverage -->
              <dc:coverage>2024-01-03T00:00:00.000000Z/2024-01-03T23:59:59.990000Z</dc:coverage>
              <!-- spatial coverage -->
              <dc:coverage>lat=41.631801 lon=15.90782 alt=30.0</dc:coverage>
            </oai_dc:dc>
          </metadata>
        </record>
```

## View Selection via `urlappend`

All representations—static or query-derived are selected using the same resolution mechanism:

```
<prefix>/<pid>?urlappend=<view>
```

Supported views include:

* `metadata` → WF Handle
* `provenance` → WF Provenance
* `data` → waveform files (default)
* `document` → readable documentation

special pid
* `search` → WF-Manifest 
* `select` → WF-Manifest 

This uniform contract ensures that identifier semantics remain stable while representations evolve.

---

### WF-Handle: what the data is

**WF Handle** is a **JSON Schema** designed to describe **Information-centric metadata**
for waveform digital objects.

It represents the **information core** of the PID-LAND architecture and provides
a **machine-actionable, FAIR-compliant description** of waveform digital objects,
independently of storage systems or delivery services.

WF Handle focuses on **what the data is**, while complementary schemas
**WF Provenance** describe **how the data was produced**.

Repository: https://github.com/INGV/wf-handle

#### Example:
```
https://hdl.handle.net/11099/be9b7af6-f71f-11ee-aae9-0242ac120004?urlappend=?q=metadata
```

---

### WF-Provenance: how the data was generated

**WF Provenance** is a **JSON Schema** designed to describe **workflow-level provenance information**
for waveform digital objects.

It is a core component of the **PID-LAND** ecosystem and complements the
**WF Handle** schema by providing a structured, machine-actionable description of
**data lineage, versioning, and processing history**.

The schema is intended for **public use**, **automatic validation**, and
**long-term traceability** of waveform digital objects.

Repository: https://github.com/INGV/wf-provenance


#### Example:
```
https://hdl.handle.net/11099/be9b7af6-f71f-11ee-aae9-0242ac120004?urlappend=?q=provenance
```

---


### Data: binary payload

In the seismological domain, the data component typically consists of timestamped 
ground motion samples stored in **miniSEED** (mSEED) **format**, a widely recognized 
standard within the International Federation of Digital Seismograph Networks (FDSN).


#### Example:
```
https://hdl.handle.net/11099/be9b7af6-f71f-11ee-aae9-0242ac120004
```

---


### Document: plain text data description

A human readable description of data ,specially of **miniSEED** the current data format used.


#### Example:
```
https://hdl.handle.net/11099/be9b7af6-f71f-11ee-aae9-0242ac120004?urlappend=?q=document
```

---

### Special PIDs: Queries as Persistent Objects

PID-LAND introduces the concept of **Special PIDs**, extending persistent identification beyond static datasets.

A **Special PID** identifies a **conceptual dataset defined by a query**, rather than by a pre-existing file.

In this model:

* the selection logic defines the object
* the PID identifies that logic
* resolution materializes a dataset view

> **The query itself becomes a persistent, citable object.**

Special PIDs are **not API calls**. They are persistent identifiers whose resolution produces a reproducible dataset derived from well-defined criteria.

Special PIDs represent query-defined datasets.
```
https://hdl.handle.net/11099/wf-search?urlappend=?q=/lat/.../lon/.../start/.../end/.../asof/...
```
They enable:

* reproducible dataset extraction
* time-aware queries (asof)
* persistent identification of dynamic data
* Machine-Actionable by Design

All outputs are:

* JSON-LD
* JSON Schema validated
* SHACL constrained


---

in summary PID-LAND enables:

* persistent identification of conceptual objects
* multiple coherent representations
* scalable metadata harvesting via OAI-PMH
* reproducible and machine-actionable data access

> It bridges discovery (OAI-PMH) and resolution (PID-LAND) in a unified, FAIR-compliant architecture.


---


### WF-Manifest: Materialized Dataset Views

When a Special PID is resolved, PID-LAND generates a **WF-Manifest**, a structured dataset representation 
encoded as an **RO-Crate JSON-LD**.

The WF-Manifest:

* represents the output of a query-defined conceptual object
* aggregates waveform files as `MediaObject` entities
* links each file to its metadata and provenance
* is fully machine-actionable and FAIR-compliant

WF-Manifest is **not a separate service**, but the natural consequence of resolving a Special PID.

Repository: https://github.com/INGV/wf-manifest

---


## Machine-Actionable by Design

All resolver outputs are:

* encoded in **JSON-LD**
* validated with **JSON Schema**
* constrained using **SHACL**

This guarantees structural validity, semantic consistency, and seamless automation across workflows.

---

## Examples

### WF-Search: Spatial and Temporal Selection

```
https://hdl.handle.net/11099/wf-search?urlappend=?q=/lat/40.7867/lon/15.9427/rad/10/start/2024-04-09/end/2024-04-10/asof/2025-01-01
```

Resolves to an aggregated RO-Crate manifest describing all matching waveform objects.

Typical use cases include regional discovery, event-based analysis, and automated data packaging.

---

### WF-Select: Deterministic Waveform Selection

```
https://hdl.handle.net/11099/wf-select?urlappend=?q=/net/IV/sta/ACER/loc//cha/HNE/start/2024-04-08/end/2024-04-10/asof/2025-01-01
```

Resolves to a deterministic dataset view, suitable for reproducible scientific workflows.

---

## Summary

PID-LAND demonstrates how persistent identifiers can act as stable entry points to **conceptual digital objects**, 
enabling multiple coherent representations, query-defined persistent datasets, and provenance-aware, machine-actionable access. 
All of this is achieved without exposing internal storage, backend services, or infrastructure details, 
making PID-LAND robust and portable across ecosystems.
