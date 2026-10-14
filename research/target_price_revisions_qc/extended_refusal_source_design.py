"""Pure public source design for an unlaunched first-refusal Mia diagnostic.

Restoration and hooks are exact byte constructions. This module does not read
files, import native/helper runtime, upload, compile or launch a strategy.
"""
from __future__ import annotations

import ast
import hashlib
import json

BUNDLE_SHA256 = "daaf0c33fd837b9896c99d1759e67454a9f3027d478879c5e60015af1f099934"
ORIGINAL_BYTES = 59931
ORIGINAL_SHA256 = "9e19a0381123f8e0d44c51b3e9dbdbe4671fe61f37b672e37f9cae8912a18a61"
RESTORED_BYTES = 60012
RESTORED_SHA256 = "454ed1e39762010997f53ef6a9f2e9064810d40a6812aae513a8fa3b090ca505"
CANDIDATE = "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
HELPER_MODULE = "extended_refusal_witness_context_successor"
HELPER_PREFIX_BYTES = 11770
HELPER_PREFIX_SHA256 = "82e7298046ab1642fb54adea98f2341b311ee6be955e16dfb345f2ea335856ba"
MAX_MAIN_CHARACTERS = 60800

ORIGINAL_IMPORT = "from extended_compressed_store import CompressedInputStore, CompressedAuditStore\n"
RESTORED_IMPORT = "from extended_compressed_store import CompressedInputStore\nfrom audit_key_recovery import CompressedAuditStore\n"
COUNTER = "        self._native_final_delisting_compatibility_exceptions = 0\n"
UNUSED_COUNTER = "        self._stale_mark_delisting_acceptances = 0\n"
IMPORT = "from extended_refusal_witness_context_successor import ContextRefusalWitness\n"
INIT_ANCHOR = "            lambda: (self.project_id, self.algorithm_id, self.get_locked()))\n"
INITIALIZATION = "        self._refusal_witness=ContextRefusalWitness(self._evidence,self.object_store,core,TradeBar)\n"
MEMBERSHIP_GUARD = "        _member_inventory(members)\n"
MEMBERSHIP_HOOK = ("        try: _member_inventory(members)\n"
    "        except ValueError as e:\n"
    "            try: self._refusal_witness.membership_context(e,etf,members,rows,now)\n"
    "            except Exception: pass\n"
    "            raise\n")
MARK_GUARD = ("            last = security.get_last_data()\n"
    "            if not isinstance(last, TradeBar):\n"
    "                raise ValueError(\"held RAW native closing mark missing\")\n"
    "            mark_clock = self._native_clock(last.end_time, \"America/New_York\")\n"
    "            if mark_clock > now or mark_clock.astimezone(NY).date().isoformat() != day:\n"
    "                raise ValueError(\"held RAW closing mark stale/future\")\n"
    "            price = native_fraction(security.price)\n"
    "            if price <= 0 or price != native_fraction(last.price):\n"
    "                raise ValueError(\"held RAW price/cache parity refused\")\n")
MARK_HOOK = ("            last=mark_clock=price=None\n"
    "            try:\n" + "".join("    " + line for line in MARK_GUARD.splitlines(keepends=True)) +
    "            except ValueError as e:\n"
    "                try: self._refusal_witness.mark_context(e,self,held,security,last,mark_clock,price,day,now)\n"
    "                except Exception: pass\n"
    "                raise\n")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _replace_once(text, before, after):
    if type(text) is not str or text.count(before) != 1: raise ValueError("exact public source anchor refused")
    return text.replace(before,after,1)


def restored_main(bundle_raw):
    if type(bundle_raw) is not bytes or _sha(bundle_raw) != BUNDLE_SHA256: raise ValueError("immutable public bundle refused")
    bundle = json.loads(bundle_raw)
    candidates = [row for row in bundle["candidates"] if row["candidate_id"] == CANDIDATE]
    if len(candidates) != 1: raise ValueError("exact OFF candidate refused")
    source = candidates[0]["files"]["main.py"]
    if type(source) is not str or len(source.encode()) != ORIGINAL_BYTES or _sha(source.encode()) != ORIGINAL_SHA256:
        raise ValueError("exact original OFF main refused")
    source = _replace_once(source,ORIGINAL_IMPORT,RESTORED_IMPORT)
    source = _replace_once(source,COUNTER,COUNTER+UNUSED_COUNTER)
    if len(source.encode()) != RESTORED_BYTES or _sha(source.encode()) != RESTORED_SHA256:
        raise ValueError("exact restored OFF main refused")
    return source


def remove_hooks(source):
    source = _replace_once(source,RESTORED_IMPORT+IMPORT,RESTORED_IMPORT)
    source = _replace_once(source,INIT_ANCHOR+INITIALIZATION,INIT_ANCHOR)
    source = _replace_once(source,MEMBERSHIP_HOOK,MEMBERSHIP_GUARD)
    source = _replace_once(source,MARK_HOOK,MARK_GUARD)
    if len(source.encode()) != RESTORED_BYTES or _sha(source.encode()) != RESTORED_SHA256:
        raise ValueError("unrecognized source delta outside approved instrumentation")
    return source


def build_main(bundle_raw):
    base = restored_main(bundle_raw)
    source = _replace_once(base,RESTORED_IMPORT,RESTORED_IMPORT+IMPORT)
    source = _replace_once(source,INIT_ANCHOR,INIT_ANCHOR+INITIALIZATION)
    source = _replace_once(source,MEMBERSHIP_GUARD,MEMBERSHIP_HOOK)
    source = _replace_once(source,MARK_GUARD,MARK_HOOK)
    if len(source) > MAX_MAIN_CHARACTERS:
        raise ValueError("diagnostic main character bound exceeded: "+str(len(source))+" > "+str(MAX_MAIN_CHARACTERS))
    if remove_hooks(source) != base: raise ValueError("public restoration proof refused")
    ast.parse(source)
    return {"schema":"tpr-ext26-unlaunched-first-refusal-source-design-v1", "candidate_id":CANDIDATE,
        "bundle_sha256":BUNDLE_SHA256, "restored_main_bytes":RESTORED_BYTES,"restored_main_sha256":RESTORED_SHA256,
        "main_py":source,"main_bytes":len(source.encode()),"main_characters":len(source),"main_sha256":_sha(source.encode()),
        "max_main_characters":MAX_MAIN_CHARACTERS,"remaining_main_characters":MAX_MAIN_CHARACTERS-len(source),
        "single_native_helper_module":HELPER_MODULE,"helper_prefix_bytes":HELPER_PREFIX_BYTES,"helper_prefix_sha256":HELPER_PREFIX_SHA256,
        "persistent_witness_instances":1,"original_guard_bytes_recovered":True,"source_executed":False,
        "new_codex_attempts":0,"new_jobs":0,"attempt_reset":False,"economics_accepted":False,"compiled_source_proven":False}
