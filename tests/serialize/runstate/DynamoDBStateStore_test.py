import os
import pickle
import tempfile

import boto3
import pytest
from moto import mock_dynamodb2

from testifycompat import assert_equal
from tron.serialize.runstate.DynamoDBStateStore import DynamoDBStateStore
from tron.serialize.runstate.shelvestore import Py2Shelf


filename = os.path.join(tempfile.mkdtemp(), 'state')


@pytest.fixture
def store():
    with mock_dynamodb2():
        dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
        table = dynamodb.create_table(
            TableName=filename.replace('/', '-'),
            KeySchema=[
                {
                    'AttributeName': 'key',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'index',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'key',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'index',
                    'AttributeType': 'N'
                },

            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 10,
                'WriteCapacityUnits': 10
            }
        )
        store = DynamoDBStateStore(filename, 'us-west-1')
        store.table = table
        # Has to be yield here for moto to work
        yield store


@pytest.fixture
def small_object():
    yield pickle.dumps({'this': 'data'})


@pytest.fixture
def large_object():
    yield pickle.dumps([i for i in range(100000)])


@pytest.mark.usefixtures("store", "small_object", "large_object")
class TestDynamoDBStateStore:
    def test_save(self, store, small_object, large_object):
        key_value_pairs = [
            (
                store.build_key("DynamoDBTest", "two"),
                small_object,
            ),
            (
                store.build_key("DynamoDBTest2", "four"),
                small_object,
            ),
        ]
        store.save(key_value_pairs)

        for key, value in key_value_pairs:
            assert_equal(store[key], value)

        for key, value in key_value_pairs:
            store._delete_item(key)
        store.cleanup()

    def test_save_more_than_4KB(self, store, small_object, large_object):
        key_value_pairs = [
            (
                store.build_key("DynamoDBTest", "two"),
                large_object
            )
        ]
        store.save(key_value_pairs)

        for key, value in key_value_pairs:
            assert_equal(store[key], value)

        for key, value in key_value_pairs:
            store._delete_item(key)
        store.cleanup()

    def test_restore_more_than_4KB(self, store, small_object, large_object):
        keys = [store.build_key("thing", i) for i in range(3)]
        value = large_object
        for key in keys:
            store[key] = value

        vals = store.restore(keys)
        for key in keys:
            assert_equal(vals[key], pickle.loads(value))

        for key in keys:
            store._delete_item(key)
        store.cleanup()

    def test_restore(self, store, small_object, large_object):
        keys = [store.build_key("thing", i) for i in range(3)]
        value = small_object
        for key in keys:
            store[key] = value

        vals = store.restore(keys)
        for key in keys:
            assert_equal(vals[key], pickle.loads(value))

        for key in keys:
            store._delete_item(key)
        store.cleanup()

    def test_delete(self, store, small_object, large_object):
        keys = [store.build_key("thing", i) for i in range(3)]
        value = large_object
        for key in keys:
            store[key] = value

        for key in keys:
            store._delete_item(key)

        for key in keys:
            assert_equal(store._get_num_of_partitions(key), 0)
        store.cleanup()

    def test_saved_to_both(self, store, small_object, large_object):
        key_value_pairs = [
            (
                store.build_key("DynamoDBTest", "two"),
                large_object
            )
        ]
        store.save(key_value_pairs)

        stored_data = Py2Shelf(filename)
        for key, value in key_value_pairs:
            assert_equal(store[key], value)
            assert_equal(stored_data[str(key.key)], value)

        for key, value in key_value_pairs:
            store._delete_item(key)
        store.cleanup()

    def test_restore_from_shelve_after_dynamodb_dies(self, store, small_object, large_object):
        key_value_pairs = [
            (
                store.build_key("DynamoDBTest", "two"),
                large_object
            )
        ]
        store.save(key_value_pairs)

        keys = [k for k, v in key_value_pairs]
        # This only cleans up data in dynamoDB
        for key in keys:
            store._delete_item(key)

        retrieved_data = store.restore(keys)
        for key in keys:
            assert_equal(retrieved_data[key], large_object)
        store.cleanup()
