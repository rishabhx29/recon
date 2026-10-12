const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatMoney(amount) {
  return money.format(amount)
}
