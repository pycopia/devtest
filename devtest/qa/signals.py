# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Collection of framework synchronous signals.

Based on the blinker package. Most testing framework activity is handled by a
simple publish-subscribe designed using these signals.
"""

from blinker import Namespace


_signals = Namespace()

# test case events
test_start = _signals.signal('test-start')
test_end = _signals.signal('test-end')
test_passed = _signals.signal('test-passed')
test_incomplete = _signals.signal('test-incomplete')
test_failure = _signals.signal('test-failure')
test_expected_failure = _signals.signal('test-expected-failure')
test_abort = _signals.signal('test-abort')
test_info = _signals.signal('test-info')
test_warning = _signals.signal('test-warning')
test_diagnostic = _signals.signal('test-diagnostic')
test_data = _signals.signal('test-data')
test_arguments = _signals.signal('test-arguments')
test_version = _signals.signal('test-version')

# runner events
run_start = _signals.signal('run-start')
run_end = _signals.signal('run-end')
run_error = _signals.signal('run-error')

# suite events
suite_start = _signals.signal('suite-start')
suite_end = _signals.signal('suite-end')
suite_info = _signals.signal('suite-info')
suite_summary = _signals.signal('suite-summary')

# informational
target_model = _signals.signal('target-model')
target_build = _signals.signal('target-build')
logdir_location = _signals.signal('logdir-location')

# reporting events
report_comment = _signals.signal('report-comment')
report_testbed = _signals.signal('report-testbed')
report_final = _signals.signal('report-final')

# services
service_want = _signals.signal('service-want')
service_dontwant = _signals.signal('service-dontwant')
service_provide = _signals.signal('service-provide')
service_start = _signals.signal('service-start')
service_stop = _signals.signal('service-stop')

# device state changes
device_change = _signals.signal('device-change')


def _test(argv):
    def listener(obj, msg=None):
        print(obj, msg)

    run_start.connect(listener)
    run_start.send(msg="A message")
    run_start.disconnect(listener)
    run_start.send(msg="No second message")


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
