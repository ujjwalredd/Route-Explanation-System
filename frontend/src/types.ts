export interface RouteRequest {
  origin_name: string;
  dest_name: string;
}

export interface FeedbackRequest {
  origin_name: string;
  dest_name: string;
  chosen_route: any;
  feedback_score: number;
}

export interface ExplainRequest {
  chosen_route: any;
  all_routes: any[];
  use_llm: boolean;
}

export interface Landmark {
  name: string;
  coords: [number, number];
}

export interface RouteStats {
  travel_time_min: number;
  distance_km: number;
}

export interface RouteProfile {
  difficult_turns: number;
  avg_road_stress: number;
  stress_label: string;
  dominant_road_type: string;
  turn_summary: string;
}

export interface Route {
  name: string;
  icon: string;
  color: string;
  description: string;
  path: number[];
  coords: [number, number][];
  edges: any[];
  stats: RouteStats;
  profile: RouteProfile;
}
