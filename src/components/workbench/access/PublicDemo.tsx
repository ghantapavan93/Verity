"use client";

import { createContext } from "react";

/**
 * Set when the workbench is a public demo (backend/app/api/access.py visit): every browser is handed a workspace of its
 * own, deleted `retentionDays` after it was made. Null when readers enter by invitation.
 */
export const PublicDemo = createContext<{ retentionDays: number } | null>(null);
