"""Base classes for tests and suites.
"""
from __future__ import annotations
# mypy: check-untyped-defs

import sys
import os
import math
from datetime import datetime, timezone
from typing import Callable, Optional, ClassVar, IO, Any, Union, Tuple, List, Dict, Set, Type, cast
from pathlib import Path

from devtest import logging

from .. import debugger
from .. import importlib
from .. import config as config_module
from ..utils import combinatorics

from ..core.types import AttrDictDefault
from ..core.constants import TestResult
from ..core.exceptions import *  # noqa
from .signals import *  # noqa

__all__ = ['TestCase', 'TestSuite', 'Scenario']

# Type annotations
Str = str
Int = int
Float = float
OptionalStr = Optional[str]
OptionalInt = Optional[int]
OptionalFloat = Optional[float]
OptionalTuple = Optional[Tuple]
OptionalList = Optional[List]
OptionalDict = Optional[Dict]
Signature = Tuple[int, str]
# temporary
TestbedRuntime = Any
UserInterface = Any


class _TestOptions:
    """A descriptor that forces OPTIONS to be class attributes that are not
    overridable by instances.
    """

    def __init__(self, initdict):
        self.OPTIONS = AttrDictDefault(initdict, default=())

    def __get__(self, instance, owner):
        return self.OPTIONS

    # This is here to make instances not able to override options, but does
    # nothing else. Attempts to set testinstance.OPTIONS are simply ignored.
    def __set__(self, instance, value):
        pass


def insert_options(klass: Type[TestCase], **kwargs):
    if type(klass) is type and issubclass(klass, TestCase):
        if "OPTIONS" not in klass.__dict__:  # type: ignore
            klass.OPTIONS = _TestOptions(kwargs)  # type: ignore
    else:
        raise ValueError("Need TestCase class.")


class Bag(dict):
    """The "bag" is a shared mapping here.

    A test case can put something into the bag, and another test pull it out.
    """


_BAG = None


def get_bag() -> Bag:
    global _BAG
    if _BAG is None:
        _BAG = Bag()
    return _BAG


class TestCase:
    """Base class for all test cases.

    Subclass this to define a new test. Define the ``procedure`` method in the
    subclass.  The test should test one specific thing. Optionally define the
    ``initialize`` and ``finalize`` methods.  Those are run before, and after
    the ``procedure`` method, respectively.
    """
    OPTIONS: ClassVar[Optional[_TestOptions]] = None  # Class, or TestCase, options
    optionslist: Optional[list[Any]] = None  # loader may set instance options
    PREREQUISITES: ClassVar[Optional[list[str]]] = None
    INTERACTIVE: ClassVar[bool] = False  # user interactive

    version = None

    def __init__(self, config, testbed, ui, name=None):
        self.config = config
        self.testbed = testbed
        self.UI = ui
        self._debug = config.flags.debug
        self._verbose = config.flags.verbose
        self._test_name = name
        self.options = self.optionslist.pop(0) if self.optionslist else {}

    @classmethod
    def set_test_options(cls):
        if cls.OPTIONS is not None:
            return
        implementation = "{}.{}".format(cls.__module__, cls.__name__)
        # Chop off "testcases." base package name for brevity.
        test_name = implementation.replace("testcases.", "")
        insert_options(cls,
                       implementation=implementation,
                       test_name=test_name,
                       repeat=1,
                       interactive=cls.INTERACTIVE,
                       bag=get_bag())
        pl = []
        if cls.PREREQUISITES:
            assert cls.PREREQUISITES is not None
            for prereq in cls.PREREQUISITES:
                if isinstance(prereq, str):
                    pl.append(_PreReq(prereq))
                elif type(prereq) is tuple:
                    pl.append(_PreReq(*prereq))
                else:
                    raise ValueError("Bad prerequisite value.")
        assert cls.OPTIONS is not None
        cls.OPTIONS.prerequisites = pl

    @property
    def bag(self) -> Dict:
        assert self.OPTIONS is not None
        return self.OPTIONS.bag

    @property
    def prerequisites(self) -> List[Str]:
        assert self.OPTIONS is not None
        return self.OPTIONS.prerequisites

    @property
    def implementation(self) -> Str:
        assert self.OPTIONS is not None
        return self.OPTIONS.implementation

    @property
    def test_name(self) -> Str:
        assert self.OPTIONS is not None
        return self._test_name or self.OPTIONS.test_name

    def get_resource(self,
                     name: Str,
                     subpackage: OptionalStr = None,
                     basepackage: OptionalStr = None) -> bytes:
        """Get a test case resource by name.

        A resource must be a file in a subpackage named "resources", inside the package of this
        test case module.

        Args:
            name: str

        Returns:
            resource as bytes.
        """
        baselist = basepackage.split(".") if basepackage else self.__class__.__module__.split(
            ".")[:-1]
        if subpackage:
            assert subpackage is not None
            baselist.append(str(subpackage))
        return importlib.get_resource(".".join(baselist), name)

    def run(self, args, kwargs) -> OptionalInt:
        """Invoke the test.

        Handles the disposition exceptions, and optional debugging. Invokes the
        `initialize` and `finalize` methods.
        """
        self._initialize()
        # Test elapsed time does not include initializer time.
        teststarttime = datetime.now(timezone.utc)
        test_start.send(self, time=teststarttime)
        test_arguments.send(self, arguments=repr_args(args, kwargs))
        if self.version:
            test_version.send(self, version=self.version)
        self.starttime = teststarttime
        rv = None
        try:
            rv = self.procedure(*args, **kwargs)
        except KeyboardInterrupt:
            self.incomplete("{}: aborted by user.".format(self.test_name))
            test_end.send(self, time=datetime.now(timezone.utc))
            self._finalize()
            raise
        except TestFailure as errval:
            self.failed(str(errval))
        except TestIncomplete as errval:
            self.incomplete(str(errval))
        # Test asserts and validation errors are based on this.
        except AssertionError as errval:
            self.failed("failed assertion: {}".format(errval))
        except TestRunAbort:
            msg = "Run aborted from {}: TestRunAbort exception.".format(self.test_name)
            test_abort.send(self, message=msg)
            test_end.send(self, time=datetime.now(timezone.utc))
            raise  # pass this one up to runner
        except TestSuiteAbort:
            self.incomplete("{}: aborted by TestSuiteAbort exception.".format(self.test_name))
            test_end.send(self, time=datetime.now(timezone.utc))
            raise  # pass this one up to suite
        except debugger.DebuggerQuit:
            self.incomplete("Quit test from debugger.")
        except:  # noqa
            ex, val, tb = sys.exc_info()
            assert ex is not None
            logging.exception_error("Error in TestCase", val)
            if self._debug:
                del tb
                debugger.from_exception(val)
            self._exception_diagnostic(ex, val)
            self.incomplete("Uncaught Exception: ({})".format(ex.__name__))
        test_end.send(self, time=datetime.now(timezone.utc))
        self._finalize()
        return rv

    def _initialize(self):
        try:
            self.initialize()
        except:  # noqa
            ex, val, tb = sys.exc_info()
            logging.exception_error("Error in TestCase.initialize", val)
            self._exception_diagnostic(ex, val)
            if self._debug:
                del tb
                debugger.from_exception(val)
            raise TestSuiteAbort("Test initialization failed!") from val

    # Run user-defined `finalize()` and catch exceptions. If an exception
    # occurs in the finalize() method (which is supposed to clean up from
    # the test and leave the DUT in the same condition as when it was
    # entered) then abort the test suite.
    # Invokes the debugger if the debug flag is set.
    def _finalize(self):
        try:
            self.finalize()
        except:  # noqa
            ex, val, tb = sys.exc_info()
            logging.exception_error("Error in TestCase.finalize", val)
            self._exception_diagnostic(ex, val)
            if self._debug:
                del tb
                debugger.from_exception(val)
            raise TestSuiteAbort("Test finalize failed!") from val

    def _exception_diagnostic(self, ex, val):
        self.diagnostic("{} ({})".format(ex.__name__, val))
        orig = val
        while val.__context__ is not None:
            val = val.__context__
            self.diagnostic(" Within: {} ({})".format(type(val).__name__, val))
        val = orig
        while val.__cause__ is not None:
            val = val.__cause__
            self.diagnostic("   From: {} ({})".format(type(val).__name__, val))

    def manual(self):
        """Perform a purely manual test according to the instructions in the
        document string.

        This allows manual tests to be mixed with automated tests. That means
        the test is human interactive, it will prompt the runner at the console
        for input. It should probably have `INTERACTIVE = True`.
        """
        UI = self.UI
        UI.write_doc(self.__class__.__doc__)
        UI.print("\nPlease perform this test according to the procedure above.")
        completed = UI.yes_no("Was it completed?")
        if completed:
            passed = UI.yes_no("Did it pass?")
            msg = UI.user_input("Comments? " if passed else "Reason? ")
            if passed:
                return self.passed("OK, user reported passed. " + msg)
            else:
                if msg:
                    self.diagnostic(msg)
                return self.failed("User reported failure.")
        else:
            msg = UI.user_input("Reason? ")
            return self.incomplete("Could not perform test. " + msg)

    def breakpoint(self):
        """Explicitly enter the debugger.

        Useful when developing new tests and you want to stop and inspect variables. Be sure to
        remove a call to this before adding for production.
        """
        self.warning(f"breakpoint: {self.test_name}. Please remove before commit.")
        breakpoint(start=2)

    # The overrideable methods follow
    def initialize(self):
        """Hook method to initialize a test.

        Override if necessary. This establishes the pre-conditions of the test.
        """
        pass

    def finalize(self):
        """Hook method when finalizing a test.

        Override if necessary. Used to clean up any state in UUT.

        """
        pass

    def procedure(self, *args, **kw):
        """The primary test method. You MUST override this in a subclass.

        This method should call one, and only one, of the methods `passed`,
        `failed`, or `incomplete`.
        """
        self.incomplete('you must define a method named "procedure" in your subclass.')

    # Result reporting methods follow
    def passed(self, message: Str = "Passed"):
        """Call this and return if the procedure() determines the test case
        passed.

        Only invoke this method if it is positively determined that the test
        case passed.
        """
        test_passed.send(self, message=message)
        return True

    def failed(self, message: Str = "Failed"):
        """Call this and return if the procedure() method determines the test
        case failed.

        Only call this if your test implementation in the procedure is positively
        sure that it does not meet the criteria. Other kinds of errors should
        return ``incomplete``. A diagnostic message should also be sent.

        If a bug is associated with this test case the result is converted into
        and EXPECTED_FAIL result.
        """
        assert self.OPTIONS is not None
        if self.OPTIONS.bugid:
            test_diagnostic.send(self,
                                 message="This failure was expected. see bug: {}.".format(
                                     self.OPTIONS.bugid))
            test_expected_failure.send(self, message=message)
        else:
            test_failure.send(self, message=message)
        return False

    def expectedfail(self, message: Str = "Expected failure"):
        """Call this and return if the procedure() failed but that was expected.

        This is used primarily for exploratory testing where you may have a
        sequence of parameterized tests where some are expected to fail past a
        certain threshold. In other words, the test fails because the
        parameters are out of spec.
        """
        test_expected_failure.send(self, message=message)
        return False

    def incomplete(self, message: Str = "Incomplete"):
        """Test could not complete.

        Call this and return if your test implementation determines that the
        test cannot be completed for whatever reason.
        """
        test_incomplete.send(self, message=message)
        return False

    def abort(self, message: Str = "Aborted"):
        """Abort the test suite.

        Some drastic error occurred, or some condition is not met, and the
        suite cannot continue. Raises the TestSuiteAbort exception.
        """
        test_abort.send(self, message=message)
        raise TestSuiteAbort(message)

    def info(self, message: Any, verbosity: OptionalInt = 0):
        """Informational messages to report.

        Like ``print()``, it can take any object and stringify it internally.
        """
        if verbosity <= self._verbose:
            test_info.send(self, message=message)

    def dut_version(self, version: Str):
        """Informational message about target version.
        """
        target_build.send(self, build=version)

    def warning(self, message: Str):
        """Report a warning to the user. Like info, but more severe.
        """
        test_warning.send(self, message=message)
        return False

    def diagnostic(self, message: Any):
        """Emit a diagnostic message.

        Call this if a failed condition is detected, and you
        want to record in the report some pertinent diagnostic information.
        """
        test_diagnostic.send(self, message=message)
        return False

    # Assertion methods make it convenient to check conditions. These names
    # match those in the standard `unittest` module for the benefit of those
    # people using that module, and is somewhat a standard across xUnit test
    # frameworks. These names are not PEP-8 for that reason.
    def assertPassed(self, arg: TestResult, message: OptionalStr = None):
        """Assert argument is a PASSED value.
        """
        if int(arg) != TestResult.PASSED:
            raise TestFailure(message or "Did not pass test.")

    def assertFailed(self, arg: TestResult, message: OptionalStr = None):
        """Assert argument is a FAILED value.
        """
        if int(arg) not in (TestResult.FAILED, TestResult.EXPECTED_FAIL):
            raise TestFailure(message or "Did not pass test.")

    def assertEqual(self, arg1: Any, arg2: Any, message: OptionalStr = None):
        """Asserts that the arguments are equal,

        Raises TestFailure if arguments are not equal. An optional message
        may be included that overrides the default message.
        """
        if arg1 != arg2:
            raise TestFailure(message or "{} != {}".format(arg1, arg2))

    def assertNotEqual(self, arg1: Any, arg2: Any, message: OptionalStr = None):
        """Asserts that the arguments are not equal,

        Raises TestFailure if arguments are equal. An optional message
        may be included that overrides the default message.
        """
        if arg1 == arg2:
            raise TestFailure(message or "{} == {}".format(arg1, arg2))

    def assertGreaterThan(self, arg1: Any, arg2: Any, message: OptionalStr = None):
        """Asserts that the first argument is greater than the second
        argument.
        """
        if not (arg1 > arg2):
            raise TestFailure(message or "{} <= {}".format(arg1, arg2))

    def assertGreaterThanOrEqual(self, arg1: Any, arg2: Any, message: OptionalStr = None):
        """Asserts that the first argument is greater or equal to the second
        argument.
        """
        if not (arg1 >= arg2):
            raise TestFailure(message or "{} < {}".format(arg1, arg2))

    def assertLessThan(self, arg1: Any, arg2: Any, message: OptionalStr = None):
        """Asserts that the first argument is less than the second
        argument.
        """
        if not (arg1 < arg2):
            raise TestFailure(message or "{} >= {}".format(arg1, arg2))

    def assertLessThanOrEqual(self, arg1: Any, arg2: Any, message: OptionalStr = None):
        """Asserts that the first argument is less than or equal to the second
        argument.
        """
        if not (arg1 <= arg2):
            raise TestFailure(message or "{} > {}".format(arg1, arg2))

    def assertTrue(self, arg: Any, message: OptionalStr = None):
        """Asserts that the argument evaluates to True by Python.

        Raises TestFailure if argument is not True according to Python truth
        testing rules.
        """
        if not arg:
            raise TestFailure(message or "{} not true.".format(arg))

    def assertFalse(self, arg: Any, message: OptionalStr = None):
        """Asserts that the argument evaluates to False by Python.

        Raises TestFailure if argument is not False according to Python truth
        testing rules.
        """
        if arg:
            raise TestFailure(message or "{} not false.".format(arg))

    def assertApproximatelyEqual(self,
                                 arg1: Any,
                                 arg2: Any,
                                 tolerance: Float = 0.05,
                                 message: OptionalStr = None):
        """Asserts that the numeric arguments are approximately equal.

        Raises TestFailure if the second argument is outside a tolerance range
        (defined by the "tolerance factor"). The default is 5% of the largest
        argument.
        """
        if not math.isclose(arg1, arg2, rel_tol=tolerance):
            raise TestFailure(
                message or
                "{} and {} not within {}% of each other.".format(arg1, arg2, tolerance * 100.0))

    def assertRaises(self,
                     exception: BaseException,
                     method: Callable,
                     args: OptionalTuple = None,
                     kwargs: OptionalDict = None,
                     message: OptionalStr = None):
        """Assert that a method and the given args will raise the given
        exception.

        Args:
            exception: The exception class the method should raise.
            method:    the method to call with the given arguments.
            args:      a tuple of positional arguments.
            kwargs:    a dictionary of keyword arguments
            message:   optional message string to be used if assertion fails.
        """
        args = args or ()
        kwargs = kwargs or {}
        try:
            method(*args, **kwargs)
        except exception:  # type: ignore
            return
        # it might raise another exception, which is marked INCOMPLETE
        raise TestFailure(message or "{!r} did not raise {!r}.".format(method, exception))

    # Some generally useful utility methods follow.

    def record_data(self, data: Any):
        """Send arbitrary data to the report.

        If the report is a persistent storage then it should save it there.

        The data should be JSON serializable object.
        """
        test_data.send(self, data=data)

    def get_filename(self, basename: OptionalStr = None, ext: Str = "log") -> Path:
        """Create a log file name.

        Return a standardized log file name with a timestamp that should be
        unique enough to not clash with other tests, and also able to correlate
        it later to the test report via the time stamp. The path points to the
        logdir location.
        """
        filename = "{}-{:%Y%m%d%H%M%S.%f}.{}".format(basename or self.test_name.replace(".", "_"),
                                                     self.starttime, ext)
        return Path(os.path.join(self.config.logdir, filename))

    def get_resultsdir_path(self, basename: Str) -> Path:
        """Create a Path to a named file in the logdir (results location).
        """
        pathname = os.path.join(self.config.logdir, basename)
        return Path(pathname)

    def open_file(self,
                  basename: OptionalStr = None,
                  ext: str = "log",
                  mode: str = "wb") -> IO[Any]:
        """Return a file object that you can write to.

        the file will be in the results location for this run.

        Args:
            basename: name of the file, without path. See get_filename for the
                      resulting name format.
            ext: file extension [default: log]
            mode: File mode. [default: wb]
        """
        fname = self.get_filename(basename, ext)
        return open(fname, mode)

    @property
    def currenttime(self) -> datetime:
        """Return current UTC time as datetime.

        Subtrace self.starttime from this to get current test running time as
        timedelta.
        """
        return datetime.now(timezone.utc)


class _PreReq:
    """A holder for test prerequisite.

    Used to hold the definition of a prerequisite test. A prerequisite is a
    Test implementation class plus any arguments it may be called with.
    No arguments means ANY arguments.
    """

    def __init__(self, implementation, args=None, kwargs=None):
        self.implementation = str(implementation)
        self.args = args or ()
        self.kwargs = kwargs or {}

    def __repr__(self):
        return "{}({!r}, args={!r}, kwargs={!r})".format(self.__class__.__name__,
                                                         self.implementation, self.args,
                                                         self.kwargs)

    def __str__(self):
        return repr_test(self.implementation, self.args, self.kwargs)


class _TestEntry:
    """Helper class to run a TestCase with arguments at some later time.

    Also helps manage prerequisite matching and verify test implementation
    correctness.

    Raises:
        raises TestImplementationError if a disposition is attempted a second
        time, or was never set.
    """

    def __init__(self, inst, args=None, kwargs=None, autoadded=False):
        self.inst = inst
        self.args = args or ()
        self.kwargs = kwargs or {}
        # True if automatically added as a prerequisite:
        self.autoadded = autoadded
        self.result = TestResult.NA
        self._signature: Optional[Signature] = None
        test_passed.connect(self._passed, sender=inst)
        test_incomplete.connect(self._incomplete, sender=inst)
        test_failure.connect(self._failure, sender=inst)
        test_expected_failure.connect(self._expected_failure, sender=inst)
        test_end.connect(self._test_end, sender=inst)
        test_abort.connect(self._abort, sender=inst)

    def _passed(self, testcase, message=None):
        if self.result != TestResult.NA:
            raise TestImplementationError("Setting PASSED when result already set.")
        self.result = TestResult.PASSED

    def _incomplete(self, testcase, message=None):
        if self.result != TestResult.NA:
            raise TestImplementationError("Setting INCOMPLETE when result already set.")
        self.result = TestResult.INCOMPLETE

    def _failure(self, testcase, message=None):
        if self.result != TestResult.NA:
            raise TestImplementationError("Setting FAILED when result already set.")
        self.result = TestResult.FAILED

    def _abort(self, testcase, message=None):
        if self.result != TestResult.NA:
            raise TestImplementationError("Setting ABORT when result already set.")
        self.result = TestResult.ABORTED

    def _expected_failure(self, testcase, message=None):
        if self.result != TestResult.NA:
            raise TestImplementationError("Setting EXPECTED_FAIL when result already set.")
        self.result = TestResult.EXPECTED_FAIL

    def _test_end(self, testcase, time=None):
        if self.result == TestResult.NA:
            raise TestImplementationError('Test case "{}" ended without setting result.'.format(
                testcase.test_name))

    def run(self):
        """Invoke the test with its arguments. The config argument is passed
        when run directly from a TestRunner, but not from a TestSuite. It is
        ignored here.
        """
        self.inst.run(self.args, self.kwargs)
        return self.result

    def __eq__(self, other):
        return self.inst == other.inst

    def match_test(self, name, args, kwargs):
        """Test signature matcher.

        Determine if a test implementation and set of arguments matches this test.
        """
        return (name, args, kwargs) == (self.inst.implementation, self.args, self.kwargs)

    def match_prerequisite(self, prereq):
        """Does this test match the specified prerequisite?

        Returns True if this test matches the supplied PreReq object.
        """
        return ((self.inst.implementation, self.args, self.kwargs) == (prereq.implementation,
                                                                       prereq.args, prereq.kwargs))

    @property
    def prerequisites(self):
        return self.inst.prerequisites

    @property
    def signature(self) -> Signature:
        """Return a unique identifier for this test entry."""
        if self._signature is None:
            arg_sig = repr((self.args, self.kwargs, self.inst.options))
            self._signature = cast(Signature, (id(self.inst.__class__), arg_sig))
        assert self._signature is not None
        return self._signature

    @property
    def test_name(self):
        return self.inst.test_name

    def __repr__(self):
        return repr_test(self.inst.implementation, self.args, self.kwargs)

    def __str__(self):
        return "{}: {}".format(self.__repr__(), self.result)


class _SuiteEntry:

    def __init__(self, suiteinst):
        self.inst = suiteinst
        self.result = TestResult.NA

    def run(self):
        self.result = self.inst.run()

    @property
    def prerequisites(self):
        return ()

    @property
    def test_name(self):
        return self.inst.test_name

    def match_prerequisite(self, prereq):
        return True


def repr_test(name: str, args: tuple, kwargs: dict) -> Str:
    """Produce repr form of test case signature.

    Returns a TestCase instantiation plus arguments as text (repr).
    """
    return "{}(...)({})".format(name, repr_args(args, kwargs))


def repr_args(args: tuple, kwargs: dict) -> Str:
    """Stringify a set of arguments.

    Arguments:
        args: tuple of arguments as a function would see it.
        kwargs: dictionary of keyword arguments as a function would see it.
    Returns:
        String as you would write it in a script.
    """
    args_s = ("{}, " if kwargs else "{}").format(", ".join(map(repr, args))) if args else ""  # noqa
    kws = ", ".join(["{}={!r}".format(it[0], it[1]) for it in kwargs.items()])
    return str(args_s) + str(kws)


class TestSuite:
    """A TestCase holder and runner.

    A TestSuite contains a set of test cases (subclasses of TestCase class)
    that are run sequentially, in the order added. It monitors abort status of
    each test, and aborts the suite if required.

    To run it, create a TestSuite object (or a subclass with some methods
    overridden), Add tests with the `add_test()` method, and then call the
    instance's run method.  The 'initialize()' method will be run with the
    arguments given when run.

    The test result if a suite is the aggregate of contained tests. If all
    tests pass the suite is passed also. If any fail, the suite is failed. If
    any are incomplete the suite is incomplete.
    """

    def __init__(self,
                 config: config_module.Config,
                 testbed: TestbedRuntime,
                 ui: UserInterface,
                 nested: bool = False,
                 name: OptionalStr = None,
                 doc: OptionalStr = None):

        self.config = config
        self.testbed = testbed
        self.UI = ui
        self._doc = doc or self.__doc__  # documentation override for reporting
        self._nested = nested
        self._debug = config.flags.debug if config is not None else 0
        cl = self.__class__
        self.implementation = "{}.{}".format(cl.__module__, cl.__name__)
        self.test_name = name or self.implementation.replace("testcases.", "")
        self.result = TestResult.NA
        self._tests: List[Union[_TestEntry, _SuiteEntry]] = []
        self._testset: Set[Signature] = set()
        self._multitestset: Set[Signature] = set()

    def __iter__(self):
        return iter(self._tests)

    def get_resource(self, name, subpackage=None):
        """Get a test suite resource by name.

        A resource must be a file in a subpackage named "resources", inside the package of this
        test suite's module.

        Args:
            name: str

        Returns:
            resource as bytes.
        """
        basepackage = self.__class__.__module__.split(".")[:-1]
        if subpackage:
            basepackage.append(str(subpackage))
        return importlib.get_resource(".".join(basepackage), name)

    def _add_with_prereq(self, entry: _TestEntry, _auto: bool = False):
        if self._debug < 3:
            for prereq in entry.inst.OPTIONS.prerequisites:
                impl = prereq.implementation
                # If only a class name is given, assume it refers to a class
                # in the same module as the defining test, and convert to full
                # path using that module.
                if "." not in impl:
                    impl = sys.modules[entry.inst.__class__.__module__].__name__ + "." + impl
                    prereq.implementation = impl
                pretestclass = importlib.get_class(impl)
                pretestclass.set_test_options()
                cf = config_module.get_config()
                preentry = _TestEntry(pretestclass(cf, self.testbed, self.UI), prereq.args,
                                      prereq.kwargs, True)
                presig, argsig = preentry.signature
                if presig not in self._multitestset:
                    self._add_with_prereq(preentry, True)
        testcaseid = entry.signature
        if not _auto:
            self._tests.append(entry)
        elif testcaseid not in self._testset:
            self._tests.append(entry)
        self._testset.add(testcaseid)

    def add_test(self,
                 _testclass: Type[TestCase],
                 args: OptionalTuple = None,
                 kwargs: OptionalDict = None,
                 name: OptionalStr = None):
        """Add a TestCase subclass and its arguments to the suite.

        Appends a test object in this suite. The test's ``procedure`` will be
        called (at the appropriate time) with the arguments supplied here. If
        the test case has a prerequisite defined it is checked for existence in
        the suite, and an exception is raised if it is not found.

        Example:

            suite.add_test(TestWithParameters, kwargs=dict(p1=0, p2=1, p3="one"))
        """
        if isinstance(_testclass, str):
            _testclass = importlib.get_class(_testclass)
        _testclass.set_test_options()
        assert _testclass.OPTIONS is not None
        if _testclass.OPTIONS.interactive and not self.config.flags.interactive:
            self.info(f"Not adding interactive test {_testclass.OPTIONS.test_name}.")
            return
        if args is None:
            argsoption = (_testclass.optionslist[0].pop("args", None)
                          if _testclass.optionslist else None)
            if argsoption is not None:
                args = argsoption if isinstance(argsoption, tuple) else (argsoption,)
            else:
                args = ()
        if kwargs is None:
            kwargs = {}
        for i in range(_testclass.OPTIONS.repeat):
            cf = config_module.get_config()
            testinstance = _testclass(cf, self.testbed, self.UI, name=name)
            entry = _TestEntry(testinstance, args, kwargs, False)
            self._add_with_prereq(entry)

    def add_test_combinations(self, _testclass: Type[TestCase], **argsets):
        """Add a multiple entries of single parameterized tests with all
        combinations of parameters supplied as lists.

        Example:

            suite.add_test_combinations(TestWithParameters,
                                        p1=[0, 1, 2],
                                        p2=[1, 2, 3],
                                        p3=["one", "two"])

        Will insert 18 test instances of this test with all combinations of
        parameters.
        """
        _testclass.set_test_options()
        cf = config_module.get_config()
        combiner = combinatorics.KeywordCounter(**argsets)
        for kwargs in combiner:
            testinstance = _testclass(cf, self.testbed, self.UI)
            entry = _TestEntry(testinstance, (), kwargs, True)
            self._add_with_prereq(entry)

    def add_tests(self,
                  _testclasslist: List[Union[Type[TestCase], Tuple[Type[TestCase], ...]]],
                  args: OptionalTuple = None,
                  kwargs: OptionalDict = None):
        """Add a list of tests at once.

        Similar to add_test method, but adds all test case classes found in the
        given list.  Arguments are common to all tests.
        If object is a tuple it should be a (testclass, tuple, dictionary) of
        positional and keyword arguments.
        """
        assert isinstance(_testclasslist, list)
        for testclass in _testclasslist:
            if type(testclass) is tuple:
                cast(Tuple, testclass)
                self.add_test(testclass[0], args=testclass[1:])
            else:
                self.add_test(cast(Type[TestCase], testclass), args=args, kwargs=kwargs)

    def add_suite(self,
                  suite: Union[TestSuite, str],
                  name: OptionalStr = None,
                  doc: OptionalStr = None):
        """Add an entire suite of tests to this suite.

        Appends an embedded test suite in this suite. This is called a sub-suite
        and is treated as a single test by this containing suite.
        """
        if isinstance(suite, str):
            cast(str, suite)
            suite = importlib.get_class(suite)
        if type(suite) is type and issubclass(suite, TestSuite):
            cast(TestSuite, suite)
            suite = suite(self.config,
                          testbed=self.testbed,
                          ui=self.UI,
                          nested=True,
                          name=name,
                          doc=doc)
        else:
            assert isinstance(suite, TestSuite), "Need a TestSuite subclass instance"
            suite.config = self.config
            suite.testbed = self.testbed
            suite.UI = self.UI
            suite._nested = True
        self._tests.append(_SuiteEntry(suite))
        return suite

    def add_scenario(self,
                     scenario: Union[Type[Scenario], str],
                     config: config_module.Config,
                     testbed: TestbedRuntime,
                     ui: UserInterface,
                     name: OptionalStr = None,
                     doc: OptionalStr = None):
        """Add another scenario to this suite being constructed.

        Gets the suite from a scenario object and adds it to this suite. You must pass through the
        three paramters given to the :ref:`get_suite` method.

        Args:
            scenario: A Scenario object.
            config: config from get_suite.
            testbed: testbed from get_suite.
            ui: UI from get_suite.
            name: (optional) override the suite class name.
            doc: (optional) override the suite doc.

        """
        if isinstance(scenario, str):
            cast(str, scenario)
            scenario = importlib.get_class(scenario)
        if type(scenario) is type and issubclass(scenario, Scenario):
            cast(Type[Scenario], scenario)
            newsuite = scenario.get_suite(config, testbed, ui)
            self.add_suite(newsuite, name, doc)

    @property
    def prerequisites(self):
        # This is here for polymorhism with TestCase objects. Always return
        # empty list.
        return ()

    @property
    def testcases(self):
        return [e.inst for e in self._tests]

    @property
    def doc(self):
        return self._doc

    def run(self) -> TestResult:
        """Invoke the test suite.

        Calling the instance is the primary way to invoke a suite of tests.

        It will then run all entries, report on interrupts, and check for
        abort conditions. It will also skip tests whose prerequisites did not
        pass. If the debug level is 2 or more then the tests are not skipped.
        """
        self._initialize()
        starttime = datetime.now(timezone.utc)
        suite_start.send(self, time=starttime)
        self.starttime = starttime
        try:
            self._run_tests()
        finally:
            endtime = datetime.now(timezone.utc)
            suite_end.send(self, time=endtime)
            self.endtime = endtime
        self._finalize()
        return self.result

    def _initialize(self):
        try:
            self.initialize()
        except KeyboardInterrupt:
            self.info("Suite aborted by user in initialize().")
            raise TestSuiteAbort("Interrupted in suite initialize.")
        except:  # noqa
            ex, val, tb = sys.exc_info()
            logging.exception_error("Error in TestSuite.initialize", val)
            if self._debug:
                del tb
                debugger.from_exception(val)
            cast(BaseException, ex)
            assert ex is not None
            self.info("Suite failed to initialize: {} ({})".format(ex.__name__, val))
            raise TestSuiteAbort("Failed to initialize") from val
        self.config.flags.interruptedb4 = 0

    def check_prerequisites(self, currententry, upto):
        """Verify that the prerequisite test passed.

        Verify any prerequisites are met at run time.
        """
        for prereq in currententry.prerequisites:
            for entry in self._tests[:upto]:
                if entry.match_prerequisite(prereq):
                    if entry.result.is_passed():
                        continue
                    else:
                        tc = currententry.inst
                        test_start.send(tc, time=datetime.now(timezone.utc))  # noqa
                        test_diagnostic.send(tc, message="Prerequisite: {}".format(prereq))  # noqa
                        test_incomplete.send(tc, message="Prerequisite did not pass.")  # noqa
                        test_end.send(tc, time=datetime.now(timezone.utc))
                        currententry.result = TestResult.INCOMPLETE
                        return False
        return True  # No prerequisite, or prereq did pass.

    def _run_tests(self):
        for i, entry in enumerate(self._tests):
            if self._debug < 2 and not self.check_prerequisites(entry, i):
                continue
            try:
                entry.run()
            except KeyboardInterrupt:
                if self._nested:
                    raise TestSuiteAbort("Sub-suite aborted by user.")
                else:
                    if self.config.flags.interruptedb4:
                        self.info("Test suite aborted by user again.")
                        raise
                    else:
                        self.config.flags.interruptedb4 += 1
                        self.info("Test suite aborted by user, continuing run.")
                        break
            except TestRunAbort:
                self.result = TestResult.ABORTED
                suite_summary.send(self, result=self.result)
                raise
            except TestSuiteAbort as err:
                errstr = err.args[0]
                self.info("Suite aborted by test: {!r} ({}).".format(entry.test_name, errstr))
                break

    def _finalize(self):
        try:
            self.finalize()
        except KeyboardInterrupt:
            if self._nested:
                raise TestSuiteAbort("Suite {!r} aborted by user in finalize().".format(
                    self.test_name))
            else:
                self.info("Suite aborted by user in finalize().")
        except:  # noqa
            ex, val, tb = sys.exc_info()
            logging.exception_error("Error in TestSuite.finalize", val)
            if self._debug:
                del tb
                debugger.from_exception(val)
            cast(BaseException, ex)
            assert ex is not None
            self.info("Suite failed to finalize: {} ({})".format(ex.__name__, val))
            if self._nested:
                raise TestSuiteAbort("subordinate suite {!r} failed to finalize.".format(
                    self.test_name))
            self.result = TestResult.ABORTED
            suite_summary.send(self, result=self.result)
            return
        resultset = {
            TestResult.PASSED: 0,
            TestResult.FAILED: 0,
            TestResult.EXPECTED_FAIL: 0,
            TestResult.INCOMPLETE: 0,
            TestResult.NA: 0
        }
        # Aggregate result for suite.
        for entry in self._tests:
            resultset[entry.result] += 1
        if resultset[TestResult.FAILED] > 0:
            self.result = TestResult.FAILED
        elif resultset[TestResult.INCOMPLETE] > 0:
            self.result = TestResult.INCOMPLETE
        elif resultset[TestResult.PASSED] > 0:
            self.result = TestResult.PASSED
        suite_summary.send(self, result=self.result)

    def __str__(self):
        s = ["Tests in suite :"]
        s.extend(list(map(str, self._tests)))
        return "\n".join(s)

    def info(self, message: str):
        """Send info message for a this suite.
        """
        suite_info.send(self, message=message)

    def record_data(self, data: Any):
        """Send arbitrary data to the report.

        If the report has a persistent storage then it should save it there.

        The data should be JSON serializable object, but may include some pickle-able objects.
        """
        test_data.send(self, data=data)

    # Overrideable interface.
    def initialize(self):
        """initialize phase handler for suite-level initialization.

        Override this if you need to do some initialization just before the
        suite is run.
        """
        pass

    def finalize(self):
        """Run the finalize phase for suite level.

        Aborts the suite on error or interrupt. If this is a sub-suite then
        TestSuiteAbort is raised so that the top-level suite can handle it.

        Override this if you need to do some additional clean-up after the
        suite is run.

        The attributes `starttime` and `endtime` are valid here.
        """
        pass


class _ScenarioWarningTest(TestCase):

    def procedure(self):
        return self.incomplete('You should override the "get_suite" static method of '
                               'your Scenario subclass.')


class Scenario:
    """A Scenario is a runable object that dynamically creates a test suite.
    """
    version = None

    @staticmethod
    def get_suite(config: config_module.Config,
                  testbed: TestbedRuntime,
                  ui: UserInterface,
                  suiteclass: Type[TestSuite] = TestSuite):
        """A TestSuite factory function.

        Override this in a subclass (as a staticmethod) and have it return some
        populated TestSuite instance.
        """
        suite = suiteclass(config, testbed=testbed, ui=ui, nested=False, name=None, doc=None)
        suite.add_test(_ScenarioWarningTest)
        return suite

    @classmethod
    def run(cls, config, testbed, ui):
        """Called by test runner.

        This calls the get_suite static method and runs the returned suite.

        Returns:
            Suite result (aggregate of test case results) as TestResult.
        """
        suite = cls.get_suite(config, testbed, ui)
        suite.run()
        return suite.result
