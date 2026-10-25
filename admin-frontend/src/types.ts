export interface AdminUser {
  id: number
  username: string
  version: string
  credits_balance: number
  is_admin: boolean
  created_at: string | null
}

export interface CreditsReport {
  by_user: { user_id: number; total_delta: number; tx_count: number }[]
  by_model: { model: string; total_delta: number; tx_count: number }[]
}

