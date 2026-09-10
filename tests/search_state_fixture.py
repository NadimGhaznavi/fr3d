"""An isolated transactional checkpoint double for search-loop unit tests."""

from copy import deepcopy


class MemorySearchStateDb:
    def __init__(self):
        self.saved = None
        self.steps = {}
        self.locked = False

    def acquire(self):
        if self.locked:
            raise RuntimeError('Another Fr3d search process owns the accounting state')
        self.locked = True

    def release(self):
        self.locked = False

    def load(self):
        return deepcopy(self.saved)

    def save(self, revision, state, step):
        actual = self.saved[0] if self.saved else 0
        if actual != revision:
            raise RuntimeError('Search accounting changed in another process')
        identity = None
        if step is not None:
            identity = step.get('id') or len(self.steps) + 1
            step = {**deepcopy(step), 'id': identity}
            self.steps[identity] = step
        active = step if step is not None and step['status'] == 'running' else None
        self.saved = deepcopy((revision + 1, state, active))
        return revision + 1, identity
