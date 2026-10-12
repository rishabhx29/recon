export function OrgSwitcher({ organizations, selected, onChange }) {
  return (
    <label className="org-switcher">
      Organization
      <select value={selected} onChange={(event) => onChange(event.target.value)}>
        {organizations.map((org) => (
          <option key={org.slug} value={org.slug}>
            {org.name}
          </option>
        ))}
      </select>
    </label>
  )
}
