"""Deterministic named-document/location retrieval for interactive Assistant."""

from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any, Callable, Sequence
from document_catalog import DocumentCatalogEntry, list_case_documents
from evidence_retrieval.document_complete import inspect_document_complete

CatalogService = Callable[..., tuple[DocumentCatalogEntry, ...]]
InspectionService = Callable[..., Any]

@dataclass(frozen=True, slots=True)
class ExplicitDocumentLocationResult:
    matched_filename: str
    source_document_instance_id: str
    location_kind: str | None
    requested_locations: tuple[int, ...]
    results: dict[str, Any]
    verified_location_pages: tuple[tuple[int, int], ...] = ()
    missing_locations: tuple[int, ...] = ()
    ambiguous_locations: tuple[int, ...] = ()

    @property
    def location_verification_complete(self) -> bool:
        return bool(self.requested_locations) and (
            len(self.verified_location_pages) == len(self.requested_locations)
            and not self.missing_locations
            and not self.ambiguous_locations
        )

_PAGE_RE = re.compile(r"\bpages?\s+(?P<start>\d{1,4})(?:\s*(?:-|–|—|to)\s*(?P<end>\d{1,4}))?", re.I)
_PARA_RE = re.compile(r"\b(?:paragraphs?|paras?\.?)\s+(?P<start>\d{1,4})(?:\s*(?:-|–|—|to)\s*(?P<end>\d{1,4}))?", re.I)
_CUES = ("grounds of resistance", "grounds of claim", "witness statement", "schedule of loss", "et3", "et1")
_GENERIC = {"the","a","an","document","documents","pdf","file","email","letter","final","copy","version","dated","date"}

def resolve_explicit_document_location(*, question: str, case_id: str,
    selected_documents: Sequence[str] | None = None,
    catalog_service: CatalogService = list_case_documents,
    inspection_service: InspectionService = inspect_document_complete,
) -> ExplicitDocumentLocationResult | None:
    if not isinstance(question, str) or not question.strip():
        return None
    catalog = tuple(catalog_service(case_id))
    matched = _resolve_unique(question, catalog, selected_documents)
    if matched is None:
        return None
    inspection = inspection_service(
        case_id=case_id,
        source_document_instance_id=matched.source_document_instance_id,
    )
    kind, locations = _location(question)
    rows = _inspection_rows(inspection, kind, locations)
    if not rows:
        return None
    verified, missing, ambiguous = _verify_requested_locations(
        inspection,
        kind,
        locations,
    )
    return ExplicitDocumentLocationResult(
        matched.original_filename,
        matched.source_document_instance_id,
        kind,
        locations,
        _to_results(rows),
        verified_location_pages=verified,
        missing_locations=missing,
        ambiguous_locations=ambiguous,
    )

def merge_explicit_with_semantic_results(explicit_results, semantic_results):
    rows, seen = [], set()
    for row in _result_rows(explicit_results) + _result_rows(semantic_results):
        if row[0] in seen:
            continue
        seen.add(row[0]); rows.append(row)
    return _to_results(rows)

def _resolve_unique(question, catalog, selected_documents):
    q, qtokens = _norm(question), set(_tokens(question))
    selected = {_norm(x) for x in (selected_documents or ()) if isinstance(x,str) and x.strip()}
    if len(selected) == 1:
        hits = tuple(e for e in catalog if _norm(e.original_filename) in selected)
        if len(hits) == 1:
            return hits[0]
    scored = []
    for e in catalog:
        fn = _norm(e.original_filename); stem = _norm(re.sub(r"\.[A-Za-z0-9]{1,8}$","",e.original_filename))
        score = 0
        if fn and fn in q: score = 10000 + len(fn)
        elif stem and stem in q: score = 9000 + len(stem)
        else:
            cue = max((len(c) for c in _CUES if c in q and c in fn), default=0)
            toks = tuple(t for t in _tokens(stem) if t not in _GENERIC and len(t) >= 3)
            mt = tuple(t for t in toks if t in qtokens)
            if cue: score = 5000 + cue*10 + len(mt)
            elif len(mt) >= 2: score = 1000 + sum(map(len,mt))
        if score: scored.append((score,e))
    if not scored: return None
    scored.sort(key=lambda x:(-x[0],x[1].original_filename.casefold(),x[1].source_document_instance_id))
    best=scored[0][0]; winners=tuple(e for s,e in scored if s==best)
    return winners[0] if len(winners)==1 else None

def _location(question):
    m=_PARA_RE.search(question)
    if m: return "paragraph", _range(m)
    m=_PAGE_RE.search(question)
    if m: return "page", _range(m)
    return None, ()

def _range(m):
    a=int(m.group("start")); b=int(m.group("end") or a)
    return tuple(range(a,b+1)) if a>0 and b>=a and b-a<=100 else ()

def _verify_requested_locations(inspection, kind, locations):
    if not kind or not locations:
        return (), (), ()

    pages = tuple(inspection.pages)
    verified = []
    missing = []
    ambiguous = []

    for location in locations:
        if kind == "page":
            matches = sorted({
                page.page_number
                for page in pages
                if page.page_number == location
            })
        elif kind == "paragraph":
            matches = sorted({
                page.page_number
                for page in pages
                if _has_para(page.text, location)
            })
        else:
            matches = []

        if len(matches) == 1:
            verified.append((location, matches[0]))
        elif not matches:
            missing.append(location)
        else:
            ambiguous.append(location)

    return tuple(verified), tuple(missing), tuple(ambiguous)


def _inspection_rows(inspection, kind, locations):
    pages=tuple(inspection.pages)
    if kind=="page" and locations:
        wanted=set(locations); pages=tuple(p for p in pages if p.page_number in wanted)
    elif kind=="paragraph" and locations:
        page_nums={p.page_number for p in pages if any(_has_para(p.text,n) for n in locations)}
        pages=tuple(p for p in pages if p.page_number in page_nums)
    rows=[]
    for p in pages:
        for c in p.chunks:
            meta={"case_id":inspection.case_id,
                  "source_document_instance_id":inspection.source_document_instance_id,
                  "source_snapshot_id":inspection.source_snapshot_id,
                  "document_name":inspection.original_filename,
                  "filename":inspection.original_filename,
                  "page":c.page_number,"page_number":c.page_number,
                  "chunk_ordinal":c.chunk_ordinal,"chunk_id":c.chunk_id,
                  "evidence_key":c.evidence_key,
                  "explicit_document_location":True,
                  "explicit_location_kind":kind or "document",
                  "explicit_requested_locations":list(locations)}
            rows.append((c.evidence_key,c.text,meta,0.0))
    return rows

def _has_para(text,n):
    return bool(re.search(rf"(?m)^\s*{n}\s*(?:[.)]|(?=\s+[A-Z]))", text or ""))

def _result_rows(results):
    ids=_first(results.get("ids")); docs=_first(results.get("documents"))
    metas=_first(results.get("metadatas")); dists=_first(results.get("distances"))
    return [(str(k), str(docs[i]) if i<len(docs) else "",
             dict(metas[i]) if i<len(metas) and isinstance(metas[i],dict) else {},
             dists[i] if i<len(dists) else None) for i,k in enumerate(ids)]

def _to_results(rows):
    return {"ids":[[r[0] for r in rows]],"documents":[[r[1] for r in rows]],
            "metadatas":[[r[2] for r in rows]],"distances":[[r[3] for r in rows]]}

def _first(v):
    return v[0] if isinstance(v,list) and v and isinstance(v[0],list) else (v if isinstance(v,list) else [])

def _tokens(v): return tuple(re.findall(r"[a-z0-9]+",v.casefold()))
def _norm(v): return " ".join(_tokens(v))
