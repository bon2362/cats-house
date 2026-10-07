import { expect, test } from '@playwright/test'

const password = process.env.CATS_HOUSE_E2E_OWNER_PASSWORD

test('the owner signs in from the header, returns to the page and signs out', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the owner sign-in check.')
  await page.goto('/')
  await page.getByRole('link', { name: 'Вход для владельца' }).click()
  await expect(page).toHaveURL(/\/login\?next=%2F$/)

  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page).toHaveURL(/\/$/)
  await expect(page.locator('cats-house-app .owner-state')).toContainText('Владелец')
  await page.getByRole('button', { name: 'Выйти' }).click()
  await expect(page.getByRole('link', { name: 'Вход для владельца' })).toBeVisible()
})

test('on a phone-width screen the header keeps the owner link fully on screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 700 })
  await page.goto('/')
  const link = page.locator('cats-house-app a.owner-link')
  await expect(link).toBeVisible()
  expect(await link.innerText()).toBe('Владелец')

  const box = await link.boundingBox()
  const headerWidth = await page.evaluate(() => document.querySelector('cats-house-app')!.shadowRoot!.querySelector('header')!.scrollWidth)

  expect(box!.x + box!.width).toBeLessThanOrEqual(390)
  expect(headerWidth).toBeLessThanOrEqual(390)
})

test('the owner opens the editor for a real person and cancels without saving', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the owner editor check.')
  await page.goto('/login?next=%2Fpeople%2Fca7750a8-ecfe-4cf4-a58c-9e9806656913')
  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/people\/ca7750a8/)

  await page.getByRole('button', { name: 'Изменить' }).click()
  await expect(page.getByLabel('Фамилия')).toHaveValue(/.+/)
  await page.getByRole('button', { name: 'Отмена' }).click()
  await expect(page.getByRole('button', { name: 'Изменить' })).toBeVisible()
})

test('the owner opens «Добавить ребёнка» for a real person and cancels', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the add-relative check.')
  await page.goto('/login?next=%2Fpeople%2Fca7750a8-ecfe-4cf4-a58c-9e9806656913')
  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/people\/ca7750a8/)

  await page.getByRole('button', { name: 'Ребёнка' }).click()
  await expect(page.getByRole('heading', { name: 'Добавить ребёнка' })).toBeVisible()
  await expect(page.getByText('Второй родитель неизвестен')).toBeVisible()
  await page.locator('cats-relative-adder').getByRole('button', { name: 'Отмена' }).first().click()
  await expect(page.getByRole('heading', { name: 'Добавить ребёнка' })).toHaveCount(0)
})

test('the owner opens the union editor for a real marriage and cancels', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the union editor check.')
  await page.goto('/login?next=%2Fpeople%2Fca7750a8-ecfe-4cf4-a58c-9e9806656913')
  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/people\/ca7750a8/)

  const block = page.locator('cats-family-editor')
  await expect(block.getByRole('heading', { name: 'Связи' })).toBeVisible()
  await block.getByRole('button', { name: 'Изменить' }).first().click()
  await expect(block.getByText('В разводе')).toBeVisible()
  await block.getByRole('button', { name: 'Отмена' }).first().click()
  await expect(block.getByText('В разводе')).toHaveCount(0)
})

test('the owner opens the biography editor for a real person and cancels', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the biography editor check.')
  await page.goto('/login?next=%2Fpeople%2Fca7750a8-ecfe-4cf4-a58c-9e9806656913')
  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/people\/ca7750a8/)

  const block = page.locator('cats-biography-section')
  await block.getByRole('button', { name: 'Изменить' }).click()
  await expect(block.getByRole('textbox', { name: 'Биография' })).toBeVisible()
  await block.getByRole('button', { name: 'Отмена' }).click()
  await expect(block.getByRole('textbox', { name: 'Биография' })).toHaveCount(0)
})
