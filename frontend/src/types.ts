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
  mode?: string;
}

export interface ArgueData {
  argumentation_framework: {
    arguments: Array<{
      id: string;
      route: string;
      dimension: string;
      polarity: string;
      strength: number;
      claim: string;
      status: string;
    }>;
    attacks: Array<{
      attacker_id: string;
      target_id: string;
      kind: string;
      weight: number;
      succeeds: boolean;
    }>;
    grounded_extension: string[];
    counts: { accepted: number; rejected: number; undecided: number; attacks_succeeded: number };
  };
  explanation: string;
  verdict: string | null;
  counterfactual: string | null;
  decisiveness: number | null;
  dimension_winners: Record<string, string>;
  recommended_by_af: string;
  af_agrees_with_chosen: boolean;
  faithfulness: { score: number; total_checked: number; violations: number };
  semantics_comparison: {
    all_semantics_agree: boolean;
    recommendations: Record<string, string>;
  };
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
