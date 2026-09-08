function formatHost(value) {
  const host = String(value || '').trim()
  if (host.startsWith('[') && host.endsWith(']')) return host
  return host.includes(':') ? `[${host}]` : host
}

export function buildDirectUrl(host, instance) {
  return `http://${formatHost(host)}:${instance.port}/`
}
