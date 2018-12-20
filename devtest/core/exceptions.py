# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""All common exceptions."""


class TestDisposition(AssertionError):
    """TestDisposition exceptions provide a convenient method of reporting valid
    test case result at any place in test case code. Usually these are negative
    results.

    This is based on AssertionError so the same assertion catcher can be
    used to indicate test failure.
    """


class TestFailure(TestDisposition):
    """Test case failed to meet the pass criteria."""


class CriticalTestFailed(TestDisposition):
    """Test case failed to meet the pass criteria, and is a critical error."""


class TestExpectedFail(TestDisposition):
    """Test case failed to meet the pass criteria, but is already known."""


class TestIncomplete(TestDisposition):
    """Test case disposition could not be determined."""


# Test must be aborted
class AbortError(Exception):
    pass


class TestSuiteAbort(AbortError):
    """Entire test suite must be aborted."""


class TestRunAbort(AbortError):
    """Entire test run must be aborted."""


# Errors in test framework
class TestError(Exception):
    """Base class for errors in the test."""


class TestRunnerError(TestError):
    """Raised for a runtime error of the test runner."""


class TestImplementationError(TestError):
    """Raised if there is something wrong with the test implementation."""


# configuration errors
class ConfigError(Exception):
    """Base class for exceptions raised when querying a configuration.
    """


class ConfigNotFoundError(ConfigError):
    """A requested value could not be found in the configuration trees.
    """


class ConfigValueError(ConfigError):
    """The value in the configuration is illegal."""


class ConfigTypeError(ConfigValueError):
    """The value in the configuration did not match the expected type.
    """


class ConfigTemplateError(ConfigError):
    """Base class for exceptions raised because of an invalid template.
    """


# database errors
class ModelError(Exception):
    """Raised when something doesn't make sense for this model.
    """


class ModelAttributeError(ModelError):
    """Raised for errors related to models with attributes."""


class ModelValidationError(ModelError):
    """Raised when altering the database with invalid values."""


# loader errors
class LoaderError(Exception):
    """Base class for test loader errors."""


class NoImplementationError(LoaderError):
    """Raised when a test object has no automated implementation defined."""


class InvalidObjectError(LoaderError):
    """Raised when an attempt is made to instantiate a test object from the
    database, but the object in the database is marked invalid.
    """


class InvalidTestError(LoaderError):
    """Raised when a test is requested that cannot be run for some
    reason.
    """


# controller errors
class ControllerError(Exception):
    """Base class for controller related errors."""


class TimeoutError(OSError):
    """Unified timeout error."""


# Errors in report objects
class ReportError(Exception):
    pass


class ReportFindError(ReportError):
    """Can't find requested report."""


if __name__ == '__main__':
    try:
        raise TestIncomplete("just testing incomplete")
    except TestDisposition as tr:
        print(tr)

    try:
        raise TestRunAbort("Testing TestRunAbort")
    except TestDisposition as tr:
        raise AssertionError("wrong exception caught.") from None
    except AbortError as aberr:
        print(aberr)
    else:
        raise AssertionError("Didn't get our exception")


# Errors related to interfacing the shells

class ShellError(Exception):
    """Base error for shell related errors."""


class ShellConnectionError(ShellError):
    """Could not make initial connection to a shell."""


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
