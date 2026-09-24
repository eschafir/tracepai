#!/bin/sh
docker rm -f tracepai >/dev/null 2>&1 && echo "TracepAI stopped" || echo "TracepAI is not running"
