import { expect, test, type Page } from '@playwright/test'

const adminToken = process.env.ADMIN_TOKEN ?? 'dev-admin-token'

function localDateTime(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    '-',
    pad(date.getMonth() + 1),
    '-',
    pad(date.getDate()),
    'T',
    pad(date.getHours()),
    ':',
    pad(date.getMinutes()),
  ].join('')
}

async function openAdmin(page: Page) {
  await page.goto('/admin')
  await page.getByLabel('Токен администратора').fill(adminToken)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByRole('heading', { name: 'Вопросы' })).toBeVisible()
}

async function createQuestion(
  page: Page,
  name: string,
  status: 'draft' | 'published',
) {
  await page.getByRole('button', { name: 'Создать' }).click()
  const editor = page.getByRole('dialog')
  await editor.getByLabel('Название', { exact: true }).fill(name)

  if (status === 'published') {
    await editor
      .getByLabel('Время показа')
      .fill(localDateTime(new Date(Date.now() - 5_000)))
    await editor.getByLabel('Длительность, сек.').fill('300')
    await editor.locator('select').selectOption('published')
  }

  await editor.getByRole('button', { name: 'Сохранить' }).click()
  const row = page.locator('tbody tr').filter({ hasText: name })
  await expect(row).toBeVisible()
  if (status === 'draft') return null

  const resultHref = await row
    .getByRole('link', { name: 'Результаты' })
    .getAttribute('href')
  const questionId = Number(resultHref?.split('/').at(-1))
  expect(questionId).toBeGreaterThan(0)
  return questionId
}

test('admin creates polls and two independent viewers vote once', async ({
  browser,
  page,
}) => {
  await openAdmin(page)

  const suffix = Date.now()
  await createQuestion(page, `E2E draft ${suffix}`, 'draft')
  const liveName = `E2E live ${suffix}`
  const questionId = await createQuestion(page, liveName, 'published')
  if (questionId === null) throw new Error('Published question has no results link')

  await page
    .getByLabel(`Показать QR-код для «${liveName}»`)
    .click()
  const shareDialog = page.getByRole('dialog')
  await expect(
    shareDialog.getByRole('heading', { name: liveName }),
  ).toBeVisible()
  await expect(shareDialog.locator('svg')).toBeVisible()
  await shareDialog.getByRole('button', { name: 'Закрыть' }).click()

  const viewerOne = await browser.newContext()
  const viewerOnePage = await viewerOne.newPage()
  await viewerOnePage.goto(`/q/${questionId}`)
  await viewerOnePage.getByRole('button', { name: 'Да' }).click()
  await expect(
    viewerOnePage.getByRole('heading', { name: 'Ответ принят' }),
  ).toBeVisible()
  await viewerOnePage.reload()
  await expect(
    viewerOnePage.getByRole('heading', { name: 'Вы уже ответили' }),
  ).toBeVisible()

  const viewerTwo = await browser.newContext()
  const viewerTwoPage = await viewerTwo.newPage()
  await viewerTwoPage.goto(`/q/${questionId}`)
  await viewerTwoPage.getByRole('button', { name: 'Нет' }).click()
  await expect(
    viewerTwoPage.getByRole('heading', { name: 'Ответ принят' }),
  ).toBeVisible()

  await page.goto(`/admin/questions/${questionId}`)
  await expect(page.getByRole('heading', { name: liveName })).toBeVisible()
  await expect(page.locator('.result-total strong')).toHaveText('2')

  await viewerOne.close()
  await viewerTwo.close()
})
