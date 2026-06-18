"use client";

import { QuickNav } from "@/components/QuickNav";
import { GeoIntelSection } from "@/components/geo-intel/GeoIntelSection";

export default function GeoIntelPage() {
  return (
    <div className="flex h-screen flex-col">
      <div className="flex items-center justify-end border-b border-[rgba(31,27,22,0.14)] bg-[#F5F1E8] px-6 py-2">
        <QuickNav current="/geo-intel" />
      </div>
      <div className="min-h-0 flex-1">
        <GeoIntelSection />
      </div>
    </div>
  );
}
