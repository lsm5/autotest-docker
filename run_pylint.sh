#!/bin/bash

MSGFMT='{msg_id}:{line:3d},{column}: {obj}: {msg}'
DISABLEMSG="I0011,R0801,R0904,R0921,R0922"
SUBTESTDISABLEMSG="I0011,R0801,R0904,E1101,E1002,R0903,F0401,C0103,C0111"
INIT_HOOK="
AP = os.environ.get('AUTOTEST_PATH', '/usr/local/autotest')
sys.path.append(os.path.abspath(AP + '/..'))
print 'Injected into path %s' % sys.path[-1]
sys.path.append(os.path.abspath('.'))
print 'Injected into path %s' % sys.path[-1]
import autotest
import autotest.common
"

# Run from top-level dir
MYDIR=$(dirname "$0")
if [ "$PWD" != "$MYDIR" ]
then
    echo "Switching to top-level directory \'$MYDIR\'"
    cd "$MYDIR"
fi

echo -e "\n\n======================================= dockertest"
find dockertest -name '*.py' -a -not -name '*_unittest*.py' | xargs \
    pylint -rn --init-hook="$INIT_HOOK" \
           --disable="$DISABLEMSG" \
           --output-format="colorized" \
           --rcfile=/dev/null \
           --msg-template="$MSGFMT"


echo -e "\n\n======================================= subtests"
INIT_HOOK="
AP = os.environ.get('AUTOTEST_PATH', '/usr/local/autotest')
sys.path.append(os.path.abspath(AP + '/..'))
print 'Injected into path %s' % sys.path[-1]
sys.path.append(os.path.abspath('.'))
print 'Injected into path %s' % sys.path[-1]
import autotest
import autotest.common
import dockertest
"
find subtests -name '*.py' -a -not -name '*_unittest*.py' | xargs \
    pylint -rn --init-hook="$INIT_HOOK" \
           --disable="$SUBTESTDISABLEMSG" \
           --output-format="colorized" \
           --rcfile=/dev/null \
           --msg-template="$MSGFMT"
