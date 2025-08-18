# Micro-Air EasyTouch Home Assistant Integration

Home Assistant custom integration for Micro-Air EasyTouch RV Thermostat using Bluetooth connectivity. This integration provides a climate entity for temperature control, device reboot functionality, and location configuration services.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Initial Setup
Install all required dependencies and development tools:
```bash
pip3 install homeassistant bluetooth-sensor-state-data flake8 isort black
```
**Expected time:** 3-5 minutes on first run (when dependencies need to be downloaded).

### Validation and Testing
Run the complete validation suite before making any changes:
```bash
# Validate integration with Home Assistant's hassfest tool
# NEVER CANCEL: This validation takes 10-15 seconds. Set timeout to 60+ seconds.
docker run --rm -v "$(pwd):/github/workspace" ghcr.io/home-assistant/hassfest

# Python syntax and style validation  
flake8 custom_components/micro_air_easytouch/
black --check custom_components/micro_air_easytouch/
isort --check-only custom_components/micro_air_easytouch/
```
**Expected times:**
- hassfest validation: 10-15 seconds
- flake8 linting: <1 second  
- black formatting check: <1 second
- isort import check: <1 second

### Code Formatting
Fix code formatting issues before committing:
```bash
# Auto-fix import sorting
isort custom_components/micro_air_easytouch/

# Auto-fix code formatting  
black custom_components/micro_air_easytouch/
```

## Validation Requirements

**CRITICAL:** Always run hassfest validation before committing changes. The integration MUST pass hassfest validation or CI will fail.

**NEVER CANCEL** any validation commands - they complete quickly but are essential for integration compatibility.

### Manual Validation Scenarios
Since this is a Bluetooth thermostat integration, complete end-to-end testing requires physical hardware. However, validate these integration points:

1. **Config Flow Testing:** Verify configuration flow can be imported and basic flow logic is intact
2. **Service Schema:** Ensure `services.yaml` has valid schema with required `target` section
3. **Climate Entity:** Verify climate entity class imports and basic properties are defined
4. **Manifest Validation:** Confirm all dependencies are properly declared

### CI Validation
The repository uses GitHub Actions workflows:
- `.github/workflows/hassfest.yaml` - Validates integration structure
- `.github/workflows/validate.yaml` - HACS validation for integration distribution

Both workflows run hassfest validation automatically on push/PR.

## Key Project Structure

### Integration Files
```
custom_components/micro_air_easytouch/
├── __init__.py              # Integration setup and coordinator
├── manifest.json            # Integration metadata and dependencies  
├── config_flow.py           # Configuration flow for setup
├── climate.py               # Main climate entity implementation
├── button.py                # Device reboot button entity
├── services.py              # Location configuration service
├── services.yaml            # Service schema definitions
├── device.py                # Base device wrapper
├── const.py                 # Integration constants
├── strings.json             # Localization strings
└── micro_air_easytouch/     # Core library package
    ├── __init__.py          # Package initialization  
    ├── const.py             # Library constants
    └── parser.py            # Bluetooth data parsing logic
```

### Configuration Files
- `hacs.json` - HACS (Home Assistant Community Store) configuration
- `manifest.json` - Defines integration domain, dependencies, and metadata

## Development Guidelines

### Code Quality Standards
- **ALWAYS** run `flake8` before committing - it checks for syntax errors and style issues
- **ALWAYS** run `black` to maintain consistent code formatting
- **ALWAYS** run `isort` to maintain consistent import ordering
- **ALWAYS** run hassfest validation to ensure Home Assistant compatibility

### Making Changes
1. Make your code changes
2. Run the complete validation suite (hassfest, flake8, black, isort)
3. Fix any validation issues
4. Test configuration flow import ability
5. Commit changes

### Common Validation Fixes
- **Flake8 errors:** Usually import issues, line length, or formatting problems
- **Black formatting:** Run `black custom_components/micro_air_easytouch/` to auto-fix
- **Import sorting:** Run `isort custom_components/micro_air_easytouch/` to auto-fix
- **hassfest errors:** Check `services.yaml` schema, `manifest.json` format, or missing required fields

### Integration Dependencies
The integration requires:
- `homeassistant` (Home Assistant core)
- `bluetooth_adapters` (declared in manifest.json)
- `bluetooth-sensor-state-data` (for Bluetooth device communication)

### NEVER Do These Things
- Do NOT try to run this integration standalone - it requires Home Assistant runtime
- Do NOT modify `manifest.json` domain or version without understanding implications
- Do NOT commit Python `__pycache__` files (they're gitignored)
- Do NOT skip hassfest validation - integration will fail in Home Assistant

## Bluetooth Integration Notes

This integration:
- Connects to Micro-Air EasyTouch thermostats via Bluetooth
- Uses `bluetooth_adapters` for device discovery and connection management
- Implements climate entity with temperature monitoring and HVAC control
- Provides device reboot functionality via button entity
- Offers location configuration service for weather display

The integration responds to physical Bluetooth device constraints - commands are slow to process and the device can only handle one connection at a time.

## Troubleshooting

### Common Issues
1. **hassfest validation fails:** Check `services.yaml` format and ensure all required fields are present
2. **Import errors during validation:** Install missing dependencies with pip3
3. **Bluetooth-related import errors:** Ensure `bluetooth-sensor-state-data` is installed
4. **Formatting errors:** Run black and isort auto-fixers

### File Reference for Common Tasks
- Check integration domain: `custom_components/micro_air_easytouch/const.py` 
- Modify service definitions: `custom_components/micro_air_easytouch/services.yaml`
- Update integration metadata: `custom_components/micro_air_easytouch/manifest.json`
- Climate entity functionality: `custom_components/micro_air_easytouch/climate.py`
- Bluetooth communication: `custom_components/micro_air_easytouch/micro_air_easytouch/parser.py`