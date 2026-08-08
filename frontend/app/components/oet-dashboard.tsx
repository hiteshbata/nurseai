import { memo } from "react"
import { DashboardHeader } from "./oet/dashboard-header"
import { FirstRunHero } from "./oet/FirstRunHero"
import { HeroCards } from "./oet/hero-cards"
import { ProgressSection } from "./oet/progress-section"
import { StatsRow } from "./oet/stats-row"
import { AdaptiveRecommendationCard } from "./oet/AdaptiveRecommendationCard"
import { ModuleProgressCard } from "./oet/ModuleProgressCard"
import { WeakSkillsList } from "./oet/WeakSkillsList"
import { CoachSummaryCard } from "./oet/CoachSummaryCard"
import { StudyPlanCard } from "./oet/StudyPlanCard"
import { StreakHeatmapCard } from "./oet/StreakHeatmapCard"
import { CriteriaPentagonCard } from "./oet/CriteriaPentagonCard"
import { MilestoneBadges } from "./oet/MilestoneBadges"
import { ProgressChart } from "./ProgressChart"
import { RecentSessions } from "./oet/recent-sessions"
import { UpgradeBanner } from "./UpgradeBanner"
import type { ModuleName, OetDashboardProps } from "./oet/types"

const MODULE_ORDER: ModuleName[] = ["speaking", "reading", "listening", "writing"]

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-2xl bg-gray-100 ${className || ''}`} />
  )
}

function HeroCardsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <SkeletonBlock className="h-36" />
      <SkeletonBlock className="h-36" />
      <SkeletonBlock className="h-36" />
    </div>
  )
}

function ChartSkeleton() {
  return (
    <SkeletonBlock className="h-64 w-full" />
  )
}

function UpgradeBannerSkeleton() {
  return <SkeletonBlock className="h-20 w-full" />
}

function OetDashboardImpl(props: OetDashboardProps) {
  return (
    // AppShell owns <main>, the page width, and the horizontal padding, so the
    // sidebar edge and the card edge line up on every app route.
    <div className="w-full py-8 lg:py-12">
      <div className="flex flex-col gap-8">
          <DashboardHeader userName={props.userName} />

          {props.sessionUsageReady === false ? (
            <UpgradeBannerSkeleton />
          ) : props.sessionUsage && (
            <UpgradeBanner
              sessionsUsed={props.sessionUsage.sessions_used}
              sessionsLimit={props.sessionUsage.sessions_limit}
              sessionsRemaining={props.sessionUsage.sessions_remaining}
              plan={props.sessionUsage.plan}
            />
          )}

          {props.statsReady === false || props.profileReady === false ? (
            <HeroCardsSkeleton />
          ) : props.totalSubmissions === 0 ? (
            <FirstRunHero
              examDateSet={props.examDateSet}
              targetBandSet={props.targetBandSet}
              onSetExamDate={props.onSetExamDate}
              savingExamDate={props.savingExamDate}
            />
          ) : (
            <>
              <HeroCards
                examDaysLeft={props.examDaysLeft}
                currentGrade={props.currentGrade}
                targetBand={props.targetBand}
                onSetExamDate={props.onSetExamDate}
                savingExamDate={props.savingExamDate}
              />

              <ProgressSection
                baselineGrade={props.baselineGrade}
                currentGrade={props.currentGrade}
                targetBand={props.targetBand}
              />

              {props.historyReady === false ? <ChartSkeleton /> : <ProgressChart data={props.scoreHistory || []} />}

              <AdaptiveRecommendationCard nextBestAction={props.nextBestAction ?? null} />

              {props.moduleAverages && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {MODULE_ORDER.map((mod) => (
                    <ModuleProgressCard key={mod} module={mod} data={props.moduleAverages![mod]} />
                  ))}
                </div>
              )}

              <StudyPlanCard />

              <CoachSummaryCard />

              <StatsRow
                totalSubmissions={props.totalSubmissions}
                averageScore={props.averageScore}
                speakingAvg={props.speakingAvg}
                thisWeekCount={props.thisWeekCount}
              />

              <WeakSkillsList skills={props.weakSkills || []} />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <StreakHeatmapCard
                  practicedDates={props.recentSubmissionDates || []}
                />
                {props.criteriaReady === false ? (
                  <SkeletonBlock className="h-64" />
                ) : (
                  <CriteriaPentagonCard
                    scores={props.criteriaScores || { fluency: null, grammar: null, pronunciation: null, empathy: null, intelligibility: null }}
                    totalSessions={props.totalSessionsScored || 0}
                  />
                )}
              </div>

              <MilestoneBadges
                streak={props.streak}
                totalSessions={props.totalSubmissions}
                currentGrade={props.currentGrade}
                baselineGrade={props.baselineGrade}
              />

              <RecentSessions recentSubmissions={props.recentSubmissions} />
            </>
          )}
      </div>
    </div>
  )
}

export const OetDashboard = memo(OetDashboardImpl)
