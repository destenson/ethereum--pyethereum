from ethereum import tester
from ethereum import utils
from ethereum import native_contracts as nc
from ethereum import abi
import logging
logging.NOTSET = logging.DEBUG

"""
test registration

test calling

test creation, how to do it in tester?
"""


class EchoContract(nc.NativeContract):
    address = utils.int_to_addr(2000)

    def _safe_call(self):
        print "echo contract called" * 10
        res, gas, data = 1, self._msg.gas, self._msg.data.data
        return res, gas, data


def test_registry():
    reg = nc.registry
    assert tester.a0 not in reg

    nc.registry.register(EchoContract)
    assert issubclass(nc.registry[EchoContract.address].im_self, EchoContract)
    nc.registry.unregister(EchoContract)


def test_echo_contract():
    nc.registry.register(EchoContract)
    s = tester.state()
    testdata = 'hello'
    print "SENDING DATA"
    r = s._send(tester.k0, EchoContract.address, 0, testdata)
    print 'DONE'
    assert r['output'] == testdata
    nc.registry.unregister(EchoContract)


def test_native_contract_instances():
    nc.registry.register(EchoContract)

    s = tester.state()
    value = 100
    create = nc.tester_create_native_contract_instance
    eci_address = create(s, tester.k0, EchoContract, value)

    assert len(eci_address) == 20
    # expect that value was transfered to the new contract
    assert s.block.get_balance(eci_address) == value
    assert s.block.get_balance(nc.CreateNativeContractInstance.address) == 0

    # test the new contract
    data = 'hello'
    r = s.send(tester.k0, eci_address, 0, data)
    assert r == data
    nc.registry.unregister(EchoContract)


class SampleNAC(nc.NativeABIContract):
    address = utils.int_to_addr(2001)

    def initialize(ctx, a='int8', c='bool', d='uint8[]'):
        "Constructor (can a constructor return anything?)"

    def afunc(ctx, a='uint16', b='uint16', returns='uint16'):
        return a * b

    def bfunc(ctx, a='uint16', returns='uint16'):
        return ctx.afunc(a, 2)  # direct native call

    def cfunc(ctx, a='uint16', returns=['uint16', 'uint16']):
        return a, a  # returns tuple

    def dfunc(ctx, a='uint16[2]', returns='uint16'):
        return a[0] * a[1]

    def void_func(ctx, a='uint16', returns=None):
        return

    def noargs_func(ctx, returns='uint16'):
        return 42

    def add_property(ctx, returns=None):
        ctx.dummy = True  # must fail

    def special_vars(ctx, returns=None):
        def _is_address(a):
            return isinstance(a, bytes) and len(a) == 20

        assert ctx.msg_data
        assert _is_address(ctx.msg_sender)
        assert ctx.msg_value == 0
        assert ctx.tx_gasprice
        assert _is_address(ctx.tx_origin)
        assert _is_address(ctx.block_coinbase)
        assert ctx.block_difficulty
        assert ctx.block_number == 0
        assert ctx.block_gaslimit
        assert 0 == ctx.get_balance(ctx.address)
        assert _is_address(ctx.address)
        assert ctx.balance == 0
        assert ctx.balance == ctx.get_balance(ctx.address)
        if ctx.block_number > 0:
            assert ctx.get_block_hash(ctx.block_number - 1) == ctx.block_prevhash

    def test_suicide(ctx, returns=None):
        ctx.suicide(ctx.block_coinbase)

    def get_address(ctx, returns='string'):
        return ctx.address


def test_nac_tester():
    assert issubclass(SampleNAC.afunc.im_class, SampleNAC)
    state = tester.state()
    nc.registry.register(SampleNAC)
    sender = tester.k0

    assert 12 == nc.tester_call_method(state, sender, SampleNAC.afunc, 3, 4)
    assert 26 == nc.tester_call_method(state, sender, SampleNAC.bfunc, 13)
    assert 4, 4 == nc.tester_call_method(state, sender, SampleNAC.cfunc, 4)
    assert 30 == nc.tester_call_method(state, sender, SampleNAC.dfunc, [5, 6])
    assert 42 == nc.tester_call_method(state, sender, SampleNAC.noargs_func)
    assert None is nc.tester_call_method(state, sender, SampleNAC.void_func, 3)
    assert None is nc.tester_call_method(state, sender, SampleNAC.special_vars)
    # values out of range must fail
    try:
        nc.tester_call_method(state, sender, SampleNAC.bfunc, -1)
    except abi.ValueOutOfBounds:
        pass
    else:
        assert False, 'must fail'
    try:
        nc.tester_call_method(state, sender, SampleNAC.afunc, 2**15, 2)
    except tester.TransactionFailed:
        pass
    else:
        assert False, 'must fail'
    try:
        nc.tester_call_method(state, sender, SampleNAC.afunc, [1], 2)
    except abi.EncodingError:
        pass
    else:
        assert False, 'must fail'


def test_nac_suicide():
    state = tester.state()
    nc.registry.register(SampleNAC)
    sender = tester.k0
    state._send(sender, SampleNAC.address, value=100)
    assert state.block.get_balance(SampleNAC.address) == 100
    assert None is nc.tester_call_method(state, sender, SampleNAC.test_suicide)
    assert state.block.get_balance(SampleNAC.address) == 0


def test_nac_add_property_fail():
    state = tester.state()
    nc.registry.register(SampleNAC)
    sender = tester.k0
    try:
        nc.tester_call_method(state, sender, SampleNAC.add_property)
    except tester.TransactionFailed:
        pass
    else:
        assert False, 'properties must not be createable'


def test_nac_instances():
    # create multiple nac instances and assert they are different contracts
    state = tester.state()
    nc.registry.register(SampleNAC)

    a0 = nc.tester_create_native_contract_instance(state, tester.k0, SampleNAC)
    a1 = nc.tester_create_native_contract_instance(state, tester.k0, SampleNAC)
    a2 = nc.tester_create_native_contract_instance(state, tester.k0, SampleNAC)

    assert a0 != a1 != a2
    assert len(a0) == 20

    # create proxies
    c0 = nc.tester_nac(state, tester.k0, a0)
    c1 = nc.tester_nac(state, tester.k0, a1)
    c2 = nc.tester_nac(state, tester.k0, a2)

    assert c0.get_address() == a0
    assert c1.get_address() == a1
    assert c2.get_address() == a2

    assert c0.afunc(5, 6) == 30
    assert c0.dfunc([4, 8]) == 32


def test_inheritance():
    pass


class OwnedSampleNAC(SampleNAC):
    address = utils.int_to_addr(2003)

    def default_method(self):
        if not self._get_storage_data('__owner__'):
            self._set_storage_data('__owner__', self.tx_origin)

    def owned(f):
        def _f(self, *args):
            if self.tx_origin == self._get_storage_data('__owner__'):
                return f(self, *args)
            raise RuntimeError('access restricted to owner')
        return _f

    def pom():
        print 'om called'

    # @owned   # does not work, as it shadows the signature
    def access(self, returns='uint8'):
        return 1


def Xtest_owned_decorator():
    state = tester.state()
    nc.registry.register(OwnedSampleNAC)
    func = nc.tester_create_native_contract_instance

    # create an instance of the contract
    owner = tester.k0
    oc_a = func(state, owner, OwnedSampleNAC)
    # the first call will go to default_method and set the owner
    # owner should be able to successfuly call .access
    oc_proxy_owner = nc.tester_nac(state, owner, oc_a)
    assert oc_proxy_owner.access() == 1

    # non owners should not be able to call .access
    non_owner = tester.k1
    oc_proxy_non_owner = nc.tester_nac(state, non_owner, oc_a)
    try:
        oc_proxy_non_owner.access()
    except tester.TransactionFailed:
        pass
    else:
        assert False, 'non owner must not access this method'


## Events #########################

class Shout(nc.ABIEvent):
    arg_types = ['uint16', 'uint16', 'uint16']
    arg_names = ['a', 'b', 'c']
    indexed = 1  # up to which arg_index args should be indexed


class EventNAC(nc.NativeABIContract):
    address = utils.int_to_addr(2005)

    def afunc(ctx, a='uint16', b='uint16', returns=None):
        Shout(ctx, a, b, 3)


def test_events():
    # create multiple nac instances and assert they are different contracts
    state = tester.state()
    nc.registry.register(EventNAC)

    # create proxies
    nc.listen_logs(state, Shout)
    c0 = nc.tester_nac(state, tester.k0, EventNAC.address)
    c0.afunc(1, 2)