import unittest
from unittest.mock import patch
from pathlib import Path
from app.config import Settings,settings
from app.services.jobs.jobs import worker_slots
from pydantic import ValidationError

class WorkerCapacity(unittest.TestCase):
    def test_explicit_size_and_auto_validation(self):
        with patch.object(settings,'worker_job_concurrency','12'):self.assertEqual(worker_slots(),12)
        for value in ['0','-1','nonsense']:
            with self.assertRaises(ValidationError):Settings(worker_job_concurrency=value,_env_file=None)

    def test_auto_uses_cgroup_budget_not_a_four_user_ceiling(self):
        def read(path,*args,**kwargs):
            return {'/sys/fs/cgroup/cpu.max':'800000 100000','/sys/fs/cgroup/memory.max':str(16*1024**3)}[str(path)]
        def sysconf(key):return {'SC_PHYS_PAGES':16*1024**3//4096,'SC_PAGE_SIZE':4096}[key]
        with patch.object(settings,'worker_job_concurrency','auto'),patch('os.cpu_count',return_value=16),patch('os.sched_getaffinity',return_value=set(range(16)),create=True),patch('os.sysconf',side_effect=sysconf),patch.object(Path,'read_text',read):
            self.assertEqual(worker_slots(),32)
