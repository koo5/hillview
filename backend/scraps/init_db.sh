sudo -u postgres psql << EOF
CREATE DATABASE hillview;
CREATE USER hillview WITH PASSWORD 'hillview';
GRANT ALL PRIVILEGES ON DATABASE hillview TO hillview;
EOF
