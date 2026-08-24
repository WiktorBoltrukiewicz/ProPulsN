/* param-write.js — write one value into the nested parameter structure.
 *
 * Geometry (02) and Simulation (03) both own values that live in the params
 * file but are edited outside the Parameters section, and both need the same
 * rule: overwrite the entry wherever it appears, and create it if the file
 * predates that parameter, rather than dropping what the user set.
 *
 * The backend applies the identical rule in
 * services/simulation_runner.py:_set_param — the two must stay in step.
 */

/**
 * @param {object} raw   nested parameter structure, modified in place
 * @param {string} key   parameter name
 * @param {*}      value new value
 * @param {{section?: string, unit?: string, description?: string}} spec
 *        where and how to create the entry when the file has no such key
 * @returns {boolean} whether anything was written
 */
export function setParam(raw, key, value, spec = {}) {
  let found = false;
  for (const section of Object.values(raw)) {
    if (!section || typeof section !== 'object') continue;
    const entry = section[key];
    if (entry && typeof entry === 'object' && 'value' in entry) {
      entry.value = value;
      found = true;
    }
  }
  if (found) return true;

  const { section, unit = '', description = '' } = spec;
  if (!section) return false;
  raw[section] = raw[section] || {};
  raw[section][key] = { value, unit, description };
  return true;
}
