import axios from 'axios';
import type { RouteRequest, FeedbackRequest, Landmark } from './types';

export interface RoutesPayload extends RouteRequest {
  departure_hour?: number | null;
}

const API_BASE = 'http://localhost:8000/api';

export const api = {
  getLandmarks: async (): Promise<Landmark[]> => {
    const res = await axios.get(`${API_BASE}/landmarks`);
    return res.data;
  },
  getCasesSummary: async () => {
    const res = await axios.get(`${API_BASE}/cases/summary`);
    return res.data;
  },
  getRoutes: async (data: RoutesPayload) => {
    const res = await axios.post(`${API_BASE}/routes`, data);
    return res.data;
  },
  submitFeedback: async (data: FeedbackRequest) => {
    const res = await axios.post(`${API_BASE}/feedback`, data);
    return res.data;
  },
};
