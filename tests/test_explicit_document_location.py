from dataclasses import dataclass
from explicit_document_location import resolve_explicit_document_location, merge_explicit_with_semantic_results

@dataclass(frozen=True)
class Entry: source_document_instance_id:str; original_filename:str
@dataclass(frozen=True)
class Chunk: page_number:int; chunk_ordinal:int; chunk_id:str; evidence_key:str; text:str
@dataclass(frozen=True)
class Page: page_number:int; text:str; chunks:tuple
@dataclass(frozen=True)
class Inspection:
    case_id:str; source_document_instance_id:str; source_snapshot_id:str
    original_filename:str; pages:tuple

def catalog(_):
    return (Entry("et3","ET3.220441.2025. Grounds of Resistance - FINAL.pdf"),
            Entry("unum","Unum return to work correspondence.pdf"))

def inspect(*,case_id,source_document_instance_id):
    assert source_document_instance_id=="et3"
    return Inspection(case_id,"et3","snap","ET3.220441.2025. Grounds of Resistance - FINAL.pdf",(
      Page(4,"27. Denial\n28. Response",(Chunk(4,0,"c27","e27","27. Denial"),Chunk(4,1,"c28","e28","28. Response"))),
      Page(5,"29. Further\n30. Denied",(Chunk(5,0,"c29","e29","29. Further"),Chunk(5,1,"c30","e30","30. Denied"))),
      Page(6,"31. Outside",(Chunk(6,0,"c31","e31","31. Outside"),)),))

def test_paragraph_range_resolves_named_governed_document():
    r=resolve_explicit_document_location(question="Compare paragraphs 27-30 of the Grounds of Resistance with Unum evidence.",
        case_id="case",catalog_service=catalog,inspection_service=inspect)
    assert r is not None and r.source_document_instance_id=="et3"
    assert r.requested_locations==(27,28,29,30)
    assert r.results["ids"]==[["e27","e28","e29","e30"]]

def test_unnamed_question_does_not_guess():
    assert resolve_explicit_document_location(question="What happened in 2005?",case_id="case",
        catalog_service=catalog,inspection_service=inspect) is None

def test_explicit_rows_precede_semantic_and_deduplicate():
    a={"ids":[["e27"]],"documents":[["exact"]],"metadatas":[[{}]],"distances":[[0.0]]}
    b={"ids":[["e27","u1"]],"documents":[["dup","unum"]],"metadatas":[[{},{}]],"distances":[[.2,.3]]}
    m=merge_explicit_with_semantic_results(a,b)
    assert m["ids"]==[["e27","u1"]] and m["documents"][0][0]=="exact"
