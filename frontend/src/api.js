const baseUrl = import.meta.env.VITE_API_URL ?? ''

export async function apiFetch(path, organization, { method = 'GET', body } = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(organization ? { 'X-Organization': organization } : {}),
    },
    body,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail ?? `request failed with ${response.status}`)
  }

  return response.json()
}
