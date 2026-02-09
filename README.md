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
| `<prefix>/<pid>?urlappend=metadata`    | WF Handle metadata (JSON-LD)                  |
| `<prefix>/<pid>?urlappend=provenance`  | WF Provenance record (JSON-LD)                |
| `<prefix>/<pid>?urlappend=version=<n>` | Specific historical version  (MSEED)          |
| `<prefix>/<pid>?urlappend=document`    | Human readble documentation  (TXT)       |
| `<prefix>/wf-search?...`               | Aggregated dataset (WF-Manifest, RO-Crate)    |
| `<prefix>/wf-select?...`               | Deterministic dataset (WF-Manifest, RO-Crate) |

All views are resolved from the **same identifier**, ensuring semantic coherence between data, metadata, and provenance.

---


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

---

### WF-Provenance: how the data was generated

**WF Provenance** is a **JSON Schema** designed to describe **workflow-level provenance information**
for waveform digital objects.

It is a core component of the **PID-LAND** ecosystem and complements the
**WF Handle** schema by providing a structured, machine-actionable description of
**data lineage, versioning, and processing history**.

The schema is intended for **public use**, **automatic validation**, and
**long-term traceability** of waveform digital objects.

---


### Data: binary payload

In the seismological domain, the data component typically consists of timestamped 
ground motion samples stored in **miniSEED** (mSEED) **format**, a widely recognized 
standard within the International Federation of Digital Seismograph Networks (FDSN).

---


### Document: plain text data description

A human readable description of data ,specially of **miniSEED** the current data format used.

---

## Special PIDs: Queries as Persistent Objects

PID-LAND introduces the concept of **Special PIDs**, extending persistent identification beyond static datasets.

A **Special PID** identifies a **conceptual dataset defined by a query**, rather than by a pre-existing file.

In this model:

* the selection logic defines the object
* the PID identifies that logic
* resolution materializes a dataset view

> **The query itself becomes a persistent, citable object.**

Special PIDs are **not API calls**. They are persistent identifiers whose resolution produces a reproducible dataset derived from well-defined criteria.

---

### Conceptual Model of a Special PID

A Special PID:

* represents a stable conceptual dataset
* resolves through the same PID-LAND endpoint
* produces a materialized dataset view
* maintains explicit links to WF Handle metadata and WF Provenance records
* remains machine-actionable and FAIR-compliant

Although resolution is dynamic, the identified object is **conceptually stable**.

Future extensions may include extraction timestamps or version anchors, enabling byte-level reproducibility.

---


### WF-Manifest: Materialized Dataset Views

When a Special PID is resolved, PID-LAND generates a **WF-Manifest**, a structured dataset representation encoded as an **RO-Crate JSON-LD**.

The WF-Manifest:

* represents the output of a query-defined conceptual object
* aggregates waveform files as `MediaObject` entities
* links each file to its metadata and provenance
* is fully machine-actionable and FAIR-compliant

WF-Manifest is **not a separate service**, but the natural consequence of resolving a Special PID.

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
https://hdl.handle.net/11099/wf-search?urlappend=search&lat=40.7867&lon=15.9427&rad=10&start=2024-04-09&end=2024-04-10
```

Resolves to an aggregated RO-Crate manifest describing all matching waveform objects.

Typical use cases include regional discovery, event-based analysis, and automated data packaging.

---

### WF-Select: Deterministic Waveform Selection

```
https://hdl.handle.net/11099/wf-select?urlappend=select&net=IV&sta=ACER&cha=HNE&start=2024-04-08&end=2024-04-10
```

Resolves to a deterministic dataset view, suitable for reproducible scientific workflows.

---

## Summary

PID-LAND demonstrates how persistent identifiers can act as stable entry points to **conceptual digital objects**, enabling multiple coherent representations, query-defined persistent datasets, and provenance-aware, machine-actionable access. All of this is achieved without exposing internal storage, backend services, or infrastructure details, making PID-LAND robust and portable across ecosystems.
