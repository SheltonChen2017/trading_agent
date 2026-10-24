"""Named native-engine identity-timing correction; no economic change or I/O.

LEAN sets AlgorithmId after Initialize and then locks the algorithm. The only
pending state here is unlocked initialization. The reviewed production caller
supplies one fixed getter for native project_id, algorithm_id and get_locked();
configured IDs, setters, default/fake IDs and generic numeric coercions do not
exist. Every journal record still uses the frozen PrivateEvidence append/export
implementation. No prefix or Object Store access exists until native binding.
Strict Python int/bool/native string ABI is deliberate; actual CLR conversion
and post-initialize lifecycle remain unverified until an actual QC successor.
"""
from __future__ import annotations

import json
import re
from types import FunctionType

from extended_core import PrivateEvidence, evidence_prefix, exact_json, CANDIDATES, FREEZE_SHA256, _hash, _keys


class DeferredPrivateEvidence:
    """Bounded initialization buffer, then immutable native-project/job custody."""
    __slots__ = ('_getter', '_static_raw', '_project', '_job', '_journal', '_faulted')

    def __init__(self, binding, native_getter):
        _keys(binding, ('candidate_id', 'config_sha256', 'freeze_sha256', 'input_hashes', 'attempt'))
        if (binding['candidate_id'] not in CANDIDATES.values() or binding['freeze_sha256'] != FREEZE_SHA256
                or type(binding['attempt']) is not int or not 1 <= binding['attempt'] <= 3
                or type(binding['input_hashes']) is not dict or not 1 <= len(binding['input_hashes']) <= 32
                or type(native_getter) is not FunctionType):
            raise ValueError('closed static evidence/native getter contract required')
        _hash(binding['config_sha256'])
        for name, identity in binding['input_hashes'].items():
            if type(name) is not str or re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', name) is None:
                raise ValueError('bounded input hash name required')
            _hash(identity)
        self._getter, self._static_raw = native_getter, exact_json(binding)
        self._project = self._job = None
        self._faulted = False
        # append() needs no namespace. Reuse the immutable original method and
        # its exact serialization, byte/record/kind bounds; never fake a job.
        self._journal = object.__new__(PrivateEvidence)
        self._journal.records, self._journal.bytes = [], 0
        self._journal.counts, self._journal.closed = {}, False
        project, _, locked = self._observe()
        self._project = project
        if locked: self.require_binding()

    def _observe(self):
        if self._faulted:
            raise ValueError('native evidence identity already refused')
        try:
            observed = self._getter()
            if type(observed) is not tuple or len(observed) != 3:
                raise ValueError('fixed native identity tuple required')
            project, job, locked = observed
            if type(project) is not int or project <= 0 or type(locked) is not bool:
                raise ValueError('strict native project/lock ABI required')
            if job is not None and (type(job) is not str or job and re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', job) is None):
                raise ValueError('strict native job ABI required')
            if self._project is not None and project != self._project:
                raise ValueError('native project changed')
            if locked and not job:
                raise ValueError('locked post-initialize native job missing')
            if self._job is not None and (job != self._job or not locked):
                raise ValueError('bound native job/lock changed')
            return project, job, locked
        except Exception:
            self._faulted = True
            raise ValueError('native evidence identity refused') from None

    def require_binding(self):
        """Explicit post-initialize gate before strategy orders or export."""
        project, job, locked = self._observe()
        if not locked:
            raise ValueError('native evidence binding requires completed locked initialization')
        if self._job is None:
            records, size, counts = self._journal.records, self._journal.bytes, self._journal.counts
            binding = {**json.loads(self._static_raw), 'project_id': project, 'job_id': job}
            # Only NOW invoke the original prefix/constructor validation.
            PrivateEvidence.__init__(self._journal, binding)
            self._journal.records, self._journal.bytes, self._journal.counts = records, size, counts
            self._job = job
        expected = {**json.loads(self._static_raw), 'project_id': self._project, 'job_id': self._job}
        expected_prefix = evidence_prefix(expected['candidate_id'], expected['config_sha256'],
            expected['attempt'], self._project, self._job)
        if exact_json(self._journal.binding) != exact_json(expected) or self._journal.prefix != expected_prefix:
            self._faulted = True
            raise ValueError('bound evidence metadata changed')
        return self._journal.prefix

    @property
    def records(self): return tuple(self._journal.records)

    @property
    def bytes(self): return self._journal.bytes

    @property
    def counts(self): return dict(self._journal.counts)

    @property
    def closed(self): return self._journal.closed

    @property
    def prefix(self): return None if self._job is None else self._journal.prefix

    @property
    def binding(self):
        return {**json.loads(self._static_raw), 'project_id': self._project, 'job_id': self._job}

    def append(self, kind, payload):
        _, _, locked = self._observe()
        if locked or self._job is not None: self.require_binding()
        PrivateEvidence.append(self._journal, kind, payload)
        self._observe()

    def export(self, store):
        self.require_binding()
        result = PrivateEvidence.export(self._journal, _NativeBoundStore(self, store))
        self.require_binding()
        return result


class _NativeBoundStore:
    """Check native custody around every original Object Store interaction."""
    __slots__ = ('_evidence', '_store')

    def __init__(self, evidence, store): self._evidence, self._store = evidence, store

    def _call(self, name, *args):
        self._evidence.require_binding()
        result = getattr(self._store, name)(*args)
        self._evidence.require_binding()
        return result

    def contains_key(self, key): return self._call('contains_key', key)

    def save(self, key, value): return self._call('save', key, value)

    def read(self, key): return self._call('read', key)
