/**
 * Shared label / tone maps for the Feature flags feature. Kept in one module so
 * the KPI grid, filters and table never re-implement them (UI mandate: cero
 * duplicación).
 */

export const TYPE_TONE = {
  feature: 'accent',
  kill: 'danger',
  rollout: 'warning',
  experiment: 'neutral',
};

export const TYPE_LABEL = {
  feature: 'Feature',
  kill: 'Kill-switch',
  rollout: 'Rollout',
  experiment: 'Experimento',
};

export const STATE_TONE = {
  on: 'success',
  off: 'neutral',
  beta: 'warning',
};

export const STATE_LABEL = {
  on: 'On',
  off: 'Off',
  beta: 'Beta',
};
