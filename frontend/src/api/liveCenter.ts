/**
 * Live match centre client: GET /api/v1/matches/{match_id}/live-center.
 * Contract: src/types/liveCenter.ts.
 */

import { apiClient } from './client';
import type { LiveCenterResponse } from '../types/liveCenter';

export async function getLiveCenter(matchId: string, signal?: AbortSignal): Promise<LiveCenterResponse> {
  return apiClient.get(`/matches/${encodeURIComponent(matchId)}/live-center`, signal).json<LiveCenterResponse>();
}
