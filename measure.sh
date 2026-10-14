#!/bin/sh
# prints avg cores used by valheim.service over N seconds
CG=/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice/valheim.service/cpu.stat
N=${1:-60}
a=$(awk '/usage_usec/{print $2}' $CG); sleep $N; b=$(awk '/usage_usec/{print $2}' $CG)
echo "avg cores: $(echo "scale=2; ($b-$a)/($N*1000000)" | bc)"
