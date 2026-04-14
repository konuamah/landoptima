# Seed Commands

## Docker Compose

### Start seed
```bash
docker-compose up -d --build seed
```

### View logs (live)
```bash
docker-compose logs -f seed
```

### View last N log lines
```bash
docker-compose logs --tail=20 seed
```

### Check container status
```bash
docker-compose ps
```

### Remove seed container
```bash
docker rm -f landoptima_seed
```

---

## Docker (direct)

### Check container status
```bash
docker ps -a --filter "name=landoptima_seed"
```

### Inspect container
```bash
docker inspect landoptima_seed
```

### View container logs
```bash
docker logs landoptima_seed
```

### Check running processes
```bash
docker top landoptima_seed
```

---

## PostgreSQL (via docker exec)

### Check row count
```bash
docker exec landoptima_db psql -U landoptima -d landoptima -c "SELECT COUNT(*) FROM ghana_grid;"
```

### Check cell_id range and total
```bash
docker exec landoptima_db psql -U landoptima -d landoptima -c "SELECT MIN(cell_id), MAX(cell_id), COUNT(*) FROM ghana_grid;"
```

### Check specific cell_id range
```bash
docker exec landoptima_db psql -U landoptima -d landoptima -c "SELECT COUNT(*) FROM ghana_grid WHERE cell_id > 414000;"
```

---

## Monitoring Loop (repeated)

```bash
sleep 30 && docker-compose logs seed 2>&1 | tail -3 && echo "---" && docker exec landoptima_db psql -U landoptima -d landoptima -c "SELECT COUNT(*) FROM ghana_grid;"
```
