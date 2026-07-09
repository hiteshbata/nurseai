import { DashboardHeader } from "./oet/dashboard-header"
import { FirstRunHero } from "./oet/FirstRunHero"
import { HeroCards } from "./oet/hero-cards"
import { ProgressSection } from "./oet/progress-section"
import { StatsRow } from "./oet/stats-row"
import { RecommendedCaseCard } from "./oet/RecommendedCaseCard"
import { CoachSummaryCard } from "./oet/CoachSummaryCard"
import { StudyPlanCard } from "./oet/StudyPlanCard"
import { StreakHeatmapCard } from "./oet/StreakHeatmapCard"
import { CriteriaPentagonCard } from "./oet/CriteriaPentagonCard"
import { MilestoneBadges } from "./oet/MilestoneBadges"
import { ProgressChart } from "./ProgressChart"
import { RecentSessions } from "./oet/recent-sessions"
import { QuickActions } from "./oet/quick-actions"
import { UpgradeBanner } from "./UpgradeBanner"
import type { OetDashboardProps } from "./oet/types"

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

export function OetDashboard(props: OetDashboardProps) {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:py-12">
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

              <RecommendedCaseCard />

              <StudyPlanCard />

              <CoachSummaryCard />

              <StatsRow
                totalSubmissions={props.totalSubmissions}
                averageScore={props.averageScore}
                speakingAvg={props.speakingAvg}
                thisWeekCount={props.thisWeekCount}
              />

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

              <QuickActions plan={props.sessionUsage?.plan} />
            </>
          )}
        </div>
      </div>
    </main>
  )
}
