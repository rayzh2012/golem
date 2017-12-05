import os
import uuid
from unittest import skipIf
from unittest.mock import patch

from requests import ConnectionError

from golem.network.hyperdrive.client import HyperdriveClient
from golem.resource.base.resourcetest import AddGetResources
from golem.resource.dirmanager import DirManager
from golem.resource.hyperdrive.resource import Resource
from golem.resource.hyperdrive.resourcesmanager import \
    HyperdriveResourceManager, DummyResourceManager
from golem.testutils import TempDirFixture


def running():
    try:
        return HyperdriveClient().id()
    except ConnectionError:
        return False


def get_resource_paths(storage, target_resources, task_id):
    resource_paths = []
    for resource in target_resources:
        path = storage.get_path(resource, task_id)
        resource_paths.append(path)
    return resource_paths


class ResourceSetUp(TempDirFixture):

    __test__ = False

    def setUp(self):
        self.dir_manager = DirManager(self.path)
        self.node_name = str(uuid.uuid4())
        self.task_id = str(uuid.uuid4())

        self.resources_dir = self.dir_manager.get_task_resource_dir(
            self.task_id)
        self.test_file = os.path.join(self.resources_dir, 'test_file.one.2')
        self.test_dir = os.path.join(self.resources_dir, 'test_dir.one.2')
        self.test_dir_file = os.path.join(self.test_dir, 'dir_file.one.2')

        self.split_resources = [
            ['test_file.one.two'],
            ['test_dir.one.two', 'dir_file.one.two']
        ]
        self.joined_resources = [
            os.path.join(*r) for r in self.split_resources
        ]
        self.target_resources = [
            os.path.join(self.resources_dir, *self.split_resources[0]),
            os.path.join(self.resources_dir, *self.split_resources[1])
        ]

        if not os.path.isdir(self.test_dir):
            os.makedirs(self.test_dir)

        open(self.test_file, 'w').close()
        with open(self.test_dir_file, 'w') as f:
            f.write("test content")


class TestResourceManagerBase(ResourceSetUp):

    def setUp(self):
        super().setUp()
        self.resource_manager = DummyResourceManager(self.dir_manager)

    def test_copy_files(self):
        old_resource_dir = self.resource_manager.storage.get_root()
        prev_content = os.listdir(old_resource_dir)

        self.dir_manager.node_name = "another" + self.node_name
        self.resource_manager.storage.copy_dir(old_resource_dir)

        assert os.listdir(self.resource_manager.storage.get_root()) == \
            prev_content

    def test_add_file(self):
        self.resource_manager.storage.clear_cache()

        self.resource_manager.add_file(self.test_dir_file, self.task_id)
        resources = self.resource_manager.storage.get_resources(self.task_id)
        assert len(resources) == 1

        with self.assertRaises(RuntimeError):
            self.resource_manager.add_files(['/.!&^%'], self.task_id)

        resources = self.resource_manager.storage.get_resources(self.task_id)
        assert len(resources) == 1

    def test_add_files(self):
        self.resource_manager.storage.clear_cache()
        self.resource_manager.add_files(self.target_resources, self.task_id)

        storage = self.resource_manager.storage
        resources = storage.get_resources(self.task_id)

        assert resources
        assert all([r.file_name in self.target_resources for r in resources])

        for resource in resources:
            assert storage.cache.get_by_path(resource.file_name) is not None
        assert storage.cache.get_by_path(str(uuid.uuid4())) is None

        storage.clear_cache()

        self.resource_manager.add_files([self.test_dir_file], self.task_id)
        assert len(storage.get_resources(self.task_id)) == 1

        with self.assertRaises(RuntimeError):
            self.resource_manager.add_files(['/.!&^%'], self.task_id)

        assert len(storage.get_resources(self.task_id)) == 1

    def test_add_task(self):
        storage = self.resource_manager.storage
        storage.clear_cache()

        resource_paths = get_resource_paths(
            self.resource_manager.storage,
            self.target_resources,
            self.task_id
        )

        self.resource_manager._add_task(resource_paths, self.task_id)
        resources = storage.get_resources(self.task_id)

        assert len(resources) == len(self.target_resources)
        assert storage.cache.get_prefix(self.task_id)
        assert storage.cache.get_resources(self.task_id)

        new_task = str(uuid.uuid4())
        self.resource_manager._add_task(resource_paths, new_task)
        assert len(resources) == len(storage.get_resources(new_task))

        self.resource_manager._add_task(resource_paths, new_task)
        assert len(storage.get_resources(new_task)) == len(resources)

    def test_remove_task(self):
        self.resource_manager.storage.clear_cache()

        resource_paths = get_resource_paths(
            self.resource_manager.storage,
            self.target_resources,
            self.task_id
        )
        self.resource_manager._add_task(resource_paths, self.task_id)
        self.resource_manager.remove_task(self.task_id)

        assert not self.resource_manager.storage.cache.get_prefix(self.task_id)
        assert not self.resource_manager.storage.get_resources(self.task_id)

    def test_to_from_wire(self):
        entries = []
        for resource in self.joined_resources:
            manager = Resource(
                str(uuid.uuid4()),
                task_id="task",
                path=os.path.dirname(resource),
                files=[os.path.basename(resource)]
            )
            entries.append(manager)

        resources_split = self.resource_manager.to_wire(entries)
        resources_joined = self.resource_manager.from_wire(resources_split)

        assert len(entries) == len(self.target_resources)
        assert all([r[0] in self.split_resources for r in resources_split])
        assert all([r[0] in self.joined_resources for r in resources_joined])

        entries = [
            ['resource', '1'],
            [None, '2'],
            None,
            [['split', 'path'], '4']
        ]
        assert self.resource_manager.from_wire(entries) == [
            ['resource', '1'],
            [os.path.join('split', 'path'), '4']
        ]


class TestHyperdriveResourceManager(TempDirFixture):

    @patch('golem.network.hyperdrive.client.HyperdriveClient.restore')
    @patch('golem.network.hyperdrive.client.HyperdriveClient.add')
    def test_add_files(self, add, restore):
        dir_manager = DirManager(self.tempdir)
        resource_manager = HyperdriveResourceManager(dir_manager)

        task_id = str(uuid.uuid4())
        resource_hash = None
        files = {str(uuid.uuid4()): 'does_not_exist'}

        # Invalid file paths
        resource_manager._add_files(files, task_id, resource_hash=resource_hash)
        assert not add.called
        assert not restore.called

        # Create files
        file_name = 'test_file'
        file_path = os.path.join(self.tempdir, file_name)
        files = {file_path: file_name}
        open(file_path, 'w').close()

        # Valid file paths, empty resource hash
        resource_manager._add_files(files, task_id, resource_hash=resource_hash)
        assert not restore.called
        assert add.called

        restore.reset_mock()
        add.reset_mock()

        # Valid file paths, non-empty resource hash
        resource_hash = str(uuid.uuid4())
        resource_manager._add_files(files, task_id, resource_hash=resource_hash)
        assert restore.called
        assert not add.called


@skipIf(not running(), "Hyperdrive daemon isn't running")
class TestHyperdriveResources(AddGetResources):
    __test__ = True
    _resource_manager_class = HyperdriveResourceManager
