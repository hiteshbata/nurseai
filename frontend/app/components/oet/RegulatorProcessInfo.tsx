export function RegulatorProcessInfo({
  regulatorName,
  sourceUrl,
}: {
  regulatorName: string
  sourceUrl: string
}) {
  return (
    <>
      <h2 id="validity" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        How long is my OET score valid?
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET itself doesn't expire, but {regulatorName} sets its own acceptance window for how old a
        result can be when you submit your application — commonly around two years for most nursing
        regulators, though this changes without notice. Confirm the current validity period on{' '}
        <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">
          {regulatorName}&apos;s own page
        </a>{' '}
        before you rely on an older result.
      </p>

      <h2 id="registration" className="text-xl font-bold text-[#0F2356] mt-8 mb-3">
        Registration process overview
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Meeting the English-language requirement is one part of registering with {regulatorName} — not
        the whole process. The typical path: confirm you meet the qualification and experience criteria{' '}
        {regulatorName} publishes, submit your application and supporting documents through their
        official portal, complete any additional assessment they require beyond the English test, then
        receive your registration once everything clears. Steps and requirements vary by regulator and
        change over time — start from{' '}
        <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">
          {regulatorName}&apos;s own registration page
        </a>{' '}
        rather than a third-party guide.
      </p>
    </>
  )
}
