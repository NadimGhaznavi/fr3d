#!/bin/bash

QUERY=$1

if [ -z $QUERY ]; then
    echo "Usage: $0 <sql-file>"
    echo "SQL files can be found and created in the base sql directory"
    exit 1
fi

mysql -u root < /opt/dev/fr3d/sql/${QUERY}.sql