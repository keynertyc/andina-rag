import { test, expect } from "@playwright/test";

const guideText =
  "# Puna\nPuna bufanda lana azul textiles. El título empieza por la marca Puna. No inventar datos. Etiquetas en minúsculas.";
const product = {
  id: "E2E-1",
  title: "BUFANDA AZUL",
  description: "Bufanda de lana azul.",
  brand: "Puna",
  category: "textiles",
  tags: ["textiles"],
};

test("ingesta, lote, revisión, conflicto, reapertura y nueva versión", async ({
  page,
  request,
}) => {
  const stamp = Date.now();
  const guideName = `Guía de prueba navegador ${stamp}`;
  const brand = `Puna E2E ${stamp}`;
  const category = `textiles-e2e-${stamp}`;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (/Content Security Policy|violates.*style-src/i.test(message.text()))
      errors.push(message.text());
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Guías de contenido" }).click();
  await expect(page.getByRole("combobox", { name: "Destino" })).toHaveText(
    "Nueva guía",
  );
  await page.getByLabel("Nombre de la guía").fill(guideName);
  await page.getByLabel("Marca (opcional)").fill(brand);
  await page.getByLabel("Categoría (opcional)").fill(category);
  await page.getByLabel("Documento", { exact: true }).setInputFiles({
    name: "guide.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(guideText),
  });
  const createdGuide = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/documents") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Subir e indexar guía" }).click();
  const guide = await (await createdGuide).json();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(
              `/api/v1/documents?document_id=${guide.document_id}`,
            )
          ).json()
        )[0].status,
    )
    .toBe("ready");
  await page.getByRole("button", { name: "Productos y lotes" }).click();
  await page.getByLabel("Archivo de productos").setInputFiles({
    name: "products.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify([{ ...product, brand, category }])),
  });
  await page.getByRole("button", { name: "Crear lote", exact: true }).click();
  await expect(page.getByText("Generada", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Revisar propuestas" }).click();
  const title = page.getByRole("textbox", { name: "Título" });
  await expect(title).toHaveValue(/Puna/);
  await title.fill("Puna Bufanda con borrador");
  await page.getByRole("button", { name: "Guías de contenido" }).click();
  await expect(
    page.getByRole("dialog", { name: "Hay cambios sin guardar" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Volver", exact: true }).click();
  await expect(title).toHaveValue("Puna Bufanda con borrador");
  const proposalId = new URL(page.url()).searchParams.get("proposal");
  const path = `/api/v1/proposals/${proposalId}`;
  const before = await (await request.get(path)).json();
  await request.patch(path, {
    data: { revision: before.revision, title: "Puna Título de otro analista" },
  });
  await page.getByRole("button", { name: "Guardar cambios" }).click();
  await expect(
    page.getByText("Hay una revisión más reciente. Tu borrador se conserva."),
  ).toBeVisible();
  await expect(title).toHaveValue("Puna Bufanda con borrador");
  await page
    .getByRole("button", { name: "Descartar borrador y cargar versión actual" })
    .click();
  await page
    .getByRole("button", { name: "Descartar borrador", exact: true })
    .click();
  await expect(title).toHaveValue("Puna Título de otro analista");
  await page.getByRole("button", { name: "Aprobar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Reabrir revisión", exact: true }),
  ).toBeVisible();
  await expect(title).toHaveAttribute("readonly");
  await expect(
    page.getByRole("button", { name: "Aprobar", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "test-results/review-desktop.png",
    fullPage: true,
  });
  const approved = await (await request.get(path)).json();
  await page.reload();
  await expect(title).toHaveAttribute("readonly");
  expect((await (await request.get(path)).json()).revision).toBe(
    approved.revision,
  );
  await page
    .getByRole("button", { name: "Reabrir revisión", exact: true })
    .click();
  await expect(title).not.toHaveAttribute("readonly");
  await title.fill("Un borrador que se descarta");
  await page.getByRole("button", { name: "Rechazar", exact: true }).click();
  await page
    .getByRole("button", { name: "Descartar cambios y rechazar", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Reabrir revisión", exact: true }),
  ).toBeVisible();
  expect((await (await request.get(path)).json()).content.title).toBe(
    "Puna Título de otro analista",
  );
  await page.getByRole("button", { name: "Guías de contenido" }).click();
  await page.getByRole("combobox", { name: "Destino" }).click();
  await page
    .getByRole("option", {
      name: `Nueva versión: ${guideName}`,
      exact: true,
    })
    .last()
    .click();
  await page.getByLabel("Documento", { exact: true }).setInputFiles({
    name: "v2.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(guideText + "\nNuevo límite de título: 70 caracteres."),
  });
  await page.getByRole("button", { name: "Subir e indexar guía" }).click();
  await expect
    .poll(async () => {
      const rows = await (
        await request.get(`/api/v1/documents?document_id=${guide.document_id}`)
      ).json();
      return rows[0].version === 2 && rows[0].status === "ready";
    })
    .toBe(true);
  await page.getByRole("button", { name: "Mesa de revisión" }).click();
  // Deep links can show historical decisions independently of the current list filter.
  await page.goto(`/?view=review&proposal=${proposalId}&status=rejected`);
  await expect(
    page.getByRole("button", { name: "Regenerar con guías vigentes" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reabrir revisión", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Regenerar con guías vigentes" })
    .click();
  await expect(page.getByText("Generada", { exact: true })).toBeVisible();
  expect((await (await request.get(path)).json()).status).toBe("rejected");
  expect(errors).toEqual([]);
});

test("nonce por respuesta, menú y diseño móvil", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (/Content Security Policy|violates.*style-src/i.test(message.text()))
      violations.push(message.text());
  });
  const response = await page.goto("/");
  const first = await page
    .locator('meta[name="csp-nonce"]')
    .getAttribute("content");
  expect(first).toMatch(/^[a-f0-9]{32}$/);
  expect(response?.headers()["content-security-policy"]).toContain(
    `'nonce-${first}'`,
  );
  expect(response?.headers()["content-security-policy"]).toContain(
    "script-src 'self';",
  );
  await page.getByRole("combobox", { name: "Estado" }).click();
  await page.getByRole("option", { name: "Aprobadas", exact: true }).click();
  await page.reload();
  expect(
    await page.locator('meta[name="csp-nonce"]').getAttribute("content"),
  ).not.toBe(first);
  await page.getByRole("combobox", { name: "Estado" }).click();
  await page.getByRole("option", { name: "Todos", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Estado" })).toHaveText(
    "Todos",
  );
  await expect(page.getByRole("textbox", { name: "Título" })).toBeVisible();
  await page.setViewportSize({ width: 360, height: 800 });
  await expect(
    page.getByRole("heading", { name: "Revisar, con evidencia." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
  expect(violations).toEqual([]);
});

test("header móvil sticky y menú accesible que protege el borrador", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/?view=guides");
  const trigger = page.getByRole("button", {
    name: "Abrir menú de navegación",
  });
  await expect(trigger).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Navegación principal" }),
  ).toBeHidden();
  await expect(
    page.getByRole("button", { name: "Ver historial" }).first(),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 900));
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(200);
  await expect
    .poll(async () => (await page.getByRole("banner").boundingBox())?.y)
    .toBe(0);
  await trigger.click();
  const menu = page.getByRole("menu", { name: "Abrir menú de navegación" });
  await expect(menu.getByRole("menuitem")).toHaveCount(3);
  await expect(
    menu.getByRole("menuitem", { name: "Guías de contenido" }),
  ).toHaveAttribute("aria-current", "page");
  await page.screenshot({
    path: "test-results/mobile-navigation.png",
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await trigger.click();
  await menu.getByRole("menuitem", { name: "Productos y lotes" }).click();
  await expect(
    page.getByRole("heading", { name: "Del catálogo a la propuesta." }),
  ).toBeVisible();
  await expect(menu).toBeHidden();
  await expect(
    page.getByRole("heading", { name: "Del catálogo a la propuesta." }),
  ).toBeInViewport();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await trigger.click();
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(menu).toBeHidden();
  await expect(trigger).toHaveCount(0);
  await page
    .getByRole("navigation", { name: "Navegación principal" })
    .getByRole("button", { name: "Guías de contenido" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Las reglas, en un solo lugar." }),
  ).toBeVisible();
  await page.setViewportSize({ width: 320, height: 800 });
  await expect(trigger).toBeVisible();
  await expect(menu).toBeHidden();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.goto("/?view=review&status=pending_review");
  const title = page.getByRole("textbox", { name: "Título" });
  await expect(title).toBeVisible();
  await title.fill("Borrador móvil sin guardar");
  await trigger.click();
  await menu.getByRole("menuitem", { name: "Guías de contenido" }).click();
  const dialog = page.getByRole("dialog", { name: "Hay cambios sin guardar" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Volver", exact: true }),
  ).toBeFocused();
  await dialog.getByRole("button", { name: "Volver", exact: true }).click();
  await expect(trigger).toBeFocused();
  await expect(title).toHaveValue("Borrador móvil sin guardar");
});
