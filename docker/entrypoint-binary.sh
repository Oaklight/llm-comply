#!/bin/sh

if [ "${1#-}" != "$1" ]; then
	set -- /usr/local/bin/llm-comply "$@"
fi

exec "$@"
