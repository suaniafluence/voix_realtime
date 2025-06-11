export function applyNoiseFilter(context, source) {
  const filter = context.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.value = 6000;
  source.connect(filter);
  return filter;
}
