import React, { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { CLASS_LABELS } from "../api.js";

const CLASS_COLORS = {
  pothole: "#ef4444",
  road_crack: "#b91c1c",
  garbage: "#10b981",
  broken_streetlight: "#f59e0b",
  water_leakage: "#3b82f6",
  damaged_traffic_sign: "#8b5cf6",
  blocked_drainage: "#06b6d4",
};

export default function MapView({ points }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const layerRef = useRef(null);

  useEffect(() => {
    if (!mapInstance.current) {
      mapInstance.current = L.map(mapRef.current, {
        center: [12.9716, 77.5946],
        zoom: 12,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(mapInstance.current);
      layerRef.current = L.layerGroup().addTo(mapInstance.current);
    }
  }, []);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();
    (points ?? []).forEach((p) => {
      const color = CLASS_COLORS[p.class_name] ?? "#64748b";
      const icon = L.divIcon({
        className: "map-pin",
        html: `<div class="pin ${p.severity}" style="background:${color}"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      });
      L.marker([p.lat, p.lon], { icon })
        .bindPopup(
          `<b>${CLASS_LABELS[p.class_name] ?? p.class_name}</b><br/>Severity: <b>${p.severity}</b><br/>Priority: <b>${p.priority_level}</b><br/>Status: ${p.status ?? "—"}`
        )
        .addTo(layer);
    });
  }, [points]);

  return <div className="map" ref={mapRef}></div>;
}
