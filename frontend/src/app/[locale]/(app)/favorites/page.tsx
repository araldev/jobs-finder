"use client";

import { useState, useMemo } from "react";
import { PageTransition } from "@/components/layout/PageTransition";
import { SearchBar } from "@/components/search/SearchBar";
import { CompactJobCard } from "@/components/jobs/CompactJobCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { useFavorites } from "@/hooks/useFavorites";
import { useOpenedJobs } from "@/lib/chat-storage";

export default function FavoritesPage() {
  const { favorites, favoriteCount } = useFavorites();
  const [search, setSearch] = useState("");
  const openedJobIds = useOpenedJobs();

  const filteredFavorites = useMemo(() => {
    if (!search.trim()) return favorites;
    const q = search.toLowerCase();
    return favorites.filter(
      (job) =>
        job.title.toLowerCase().includes(q) ||
        job.company.toLowerCase().includes(q),
    );
  }, [favorites, search]);

  return (
    <PageTransition>
      {favorites.length > 0 && (
        <div className="mb-4 max-w-md">
          <SearchBar
            value={search}
            onChange={setSearch}
            placeholder="Filter favorites..."
          />
        </div>
      )}

      {filteredFavorites.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredFavorites.map((job, i) => (
            <CompactJobCard key={job.id} job={job} index={i} openedJobIds={openedJobIds} />
          ))}
        </div>
      ) : favorites.length > 0 ? (
        <EmptyState
          variant="no-results"
          title="No matching favorites"
          description="Try a different search term"
        />
      ) : (
        <EmptyState
          variant="empty"
          title="No favorites yet"
          description="Browse jobs and save them with the heart icon."
        />
      )}
    </PageTransition>
  );
}
