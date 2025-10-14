#!/bin/sh

# 设置默认的用户ID和组ID
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# 修改 appuser 组的 GID
if [ "$(getent group appuser | cut -d: -f3)" != "$PGID" ]; then
    echo "Changing appuser GID to $PGID"
    groupmod -o -g "$PGID" appuser
fi

# 修改 appuser 用户的 UID
if [ "$(getent passwd appuser | cut -d: -f3)" != "$PUID" ]; then
    echo "Changing appuser UID to $PUID"
    usermod -o -u "$PUID" appuser
fi

# 确保 /app 目录的所有权正确
# 这对于防止在ID更改后出现权限问题很重要
echo "Updating /app ownership ..."
chown -R appuser:appuser /app

echo "
-------------------------------------
User UID: $(id -u appuser)
User GID: $(id -g appuser)
-------------------------------------
"

# 以 appuser 的身份执行传递给脚本的任何命令
exec gosu appuser "$@"