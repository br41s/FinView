"use client";

import { GeoIntelSection } from "@/components/geo-intel/GeoIntelSection";

export default function GeoIntelPage() {
  return (
    <div className="flex min-h-screen flex-col lg:h-screen">
      <div className="flex-1 lg:min-h-0">
        <GeoIntelSection />
      </div>
    </div>
  );
}
