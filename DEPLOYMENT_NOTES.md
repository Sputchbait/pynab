# Pynab Deployment Notes

## Critical Configuration Changes Required

When deploying this Pynab fork, the following configuration changes are **REQUIRED** for proper operation:

### 1. Firewall Configuration (CRITICAL)

**All Pynab services** (nabweatherd, nabclockd, nabairqualityd, etc.) communicate with nabd via localhost port 10543. The firewall MUST allow loopback traffic.

```bash
# Allow all localhost/loopback traffic (REQUIRED)
sudo iptables -I INPUT 1 -i lo -j ACCEPT

# Allow local network access to nabd
sudo iptables -A INPUT -p tcp -s 192.168.1.0/24 --dport 10543 -j ACCEPT

# Block external access to nabd
sudo iptables -A INPUT -p tcp --dport 10543 -j DROP

# Save rules (Debian/Ubuntu with iptables-persistent)
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

**Without the loopback rule, NO services will be able to connect to nabd.**

### 2. Service Configuration Files

Each service's `.conf` file must use `NABD_HOST=127.0.0.1` (NOT `0.0.0.0`).

**Example**: `/opt/pynab/nabweatherd/nabweatherd.conf`
```
LOGLEVEL=INFO
NABD_HOST=127.0.0.1
```

Check all service config files:
```bash
grep -r "NABD_HOST" /opt/pynab/*/
```

If any show `NABD_HOST=0.0.0.0`, update them:
```bash
sudo sed -i 's/NABD_HOST=0.0.0.0/NABD_HOST=127.0.0.1/g' /opt/pynab/*/*.conf
```

### 3. Verify Setup

After deployment, verify all services can connect:

```bash
# Check all services are running
systemctl list-units 'nab*'

# Check for connection errors
sudo journalctl -u nabweatherd -n 50 | grep -i "timeout\|connect\|error"
sudo journalctl -u nabclockd -n 50 | grep -i "timeout\|connect\|error"

# Verify nabd is listening
sudo netstat -tlnp | grep 10543
```

Expected: All services show `Active: active (running)`, no timeout errors.

---

## Weather Service Specific Changes

### Open-Meteo API Integration

This fork uses **Open-Meteo API** instead of the original Météo-France API.

**Location Data Format Support**:
- Old format: `{"lat": 47.5301, "lon": -122.03262, ...}`
- New format: `{"latitude": 47.5301, "longitude": -122.03262, ...}`
- **Both are now supported** (as of commit 66e5682)

**Weather Settings**:
- Location search uses Open-Meteo Geocoding API
- Forecast data from Open-Meteo Forecast API
- WMO weather codes mapped to animation classes
- No API key required (free tier sufficient)

**Testing**:
```bash
cd /opt/pynab
source venv/bin/activate
python3 test_weather_integration.py
```

---

## Troubleshooting

### Services Won't Connect to nabd

**Symptom**: `TimeoutError: [Errno 110] Connect call failed ('127.0.0.1', 10543)`

**Cause**: Firewall blocking localhost

**Fix**:
```bash
sudo iptables -I INPUT 1 -i lo -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
sudo systemctl restart nab*
```

### Weather Animations Not Displaying

**Checklist**:
1. ✅ Location configured in web UI
2. ✅ nabweatherd service running
3. ✅ Animation type NOT set to "Nothing"
4. ✅ Firewall allows localhost
5. ✅ NABD_HOST=127.0.0.1 in config

**Debug**:
```bash
# Enable debug logging
sudo sed -i 's/LOGLEVEL=INFO/LOGLEVEL=DEBUG/' /opt/pynab/nabweatherd/nabweatherd.conf
sudo systemctl restart nabweatherd

# Watch logs
sudo journalctl -u nabweatherd -f

# Test manually
# (from development machine with test script)
./test_weather_manually.py today
```

---

## Known Issues

### Raspberry Pi Zero W Performance
- CPU: 1GHz single-core
- RAM: 512MB
- Services may take 30-60s to start after boot
- Weather API calls may timeout under load
- Consider reducing service count for better performance

### Network Requirements
- Open-Meteo API: https://api.open-meteo.com (ports 80/443)
- Geocoding API: https://geocoding-api.open-meteo.com (ports 80/443)
- No firewall issues expected (these are outbound connections)

---

## Deployment Checklist

- [ ] Firewall: loopback interface allowed (`iptables -I INPUT 1 -i lo -j ACCEPT`)
- [ ] Firewall: rules saved to `/etc/iptables/rules.v4`
- [ ] All service configs use `NABD_HOST=127.0.0.1`
- [ ] nabd service running and listening on port 10543
- [ ] All nab* services running without connection errors
- [ ] Weather service: location configured
- [ ] Weather service: test triggers animations successfully
- [ ] Web interface accessible
- [ ] RFID reader functional (if using)

---

## Reference

- Original Pynab: https://github.com/nabaztag2018/pynab
- Open-Meteo API: https://open-meteo.com
- WMO Weather Codes: https://www.nodc.noaa.gov/archive/arc0021/0002199/1.1/data/0-data/HTML/WMO-CODE/WMO4677.HTM

---

**Last Updated**: 2026-06-09  
**Deployed On**: Aaron's Bunny (192.168.1.234)
