import { Suspense } from "react"

import { ProductPage } from "./product-page"

// Static hosts can only emit paths known at build time. Real catalogue ids are
// loaded in the browser; GitHub Pages builds the placeholder route and passes
// the id as a query param. A normal server build still renders any id.
export function generateStaticParams() {
  return [{ id: "placeholder" }]
}

export const dynamicParams = true

export default function Page() {
  return (
    <Suspense>
      <ProductPage />
    </Suspense>
  )
}
