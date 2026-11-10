"use client"

import { useCallback, useEffect, useState } from "react"

import { api } from "@/lib/api"

export function useAdminAuth() {
  const [state, setState] = useState<{ loading: boolean; configured: boolean; authenticated: boolean; username: string | null; csrf: string | null }>({
    loading: true, configured: true, authenticated: false, username: null, csrf: null,
  })
  const refresh = useCallback(async () => {
    try {
      const s = await api.admin.status()
      setState({ loading: false, ...s })
    } catch {
      setState((p) => ({ ...p, loading: false }))
    }
  }, [])
  useEffect(() => {
    refresh()
  }, [refresh])
  return { ...state, refresh, setState }
}
