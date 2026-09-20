import { useState } from 'react';
import { TabPanel, Tabs } from '../ui';
import OverviewPanel from './panels/OverviewPanel';
import CompetitorsPanel from './panels/CompetitorsPanel';
import PeoplePanel from './panels/PeoplePanel';
import NewsPanel from './panels/NewsPanel';
import SwotPanel from './panels/SwotPanel';
import ContentPanel from './panels/ContentPanel';
import RiskPanel from './panels/RiskPanel';
import ContactsPanel from './panels/ContactsPanel';

const TABS = [
  { id: 'overview', label: 'Overview', Panel: OverviewPanel },
  { id: 'competitors', label: 'Competitors', Panel: CompetitorsPanel },
  { id: 'people', label: 'People & Culture', Panel: PeoplePanel },
  { id: 'news', label: 'News & Events', Panel: NewsPanel },
  { id: 'swot', label: 'SWOT', Panel: SwotPanel },
  { id: 'content', label: 'Content Strategy', Panel: ContentPanel },
  { id: 'risk', label: 'Risk & Finance', Panel: RiskPanel },
  { id: 'contacts', label: 'Contacts', Panel: ContactsPanel },
];

export default function IntelTabs({ report }) {
  const [active, setActive] = useState('overview');
  const current = TABS.find((t) => t.id === active) || TABS[0];
  const { Panel } = current;
  return (
    <div>
      <Tabs tabs={TABS} value={active} onChange={setActive} idPrefix="intel" label="Company intelligence sections" />
      <TabPanel idPrefix="intel" id={current.id}>
        <Panel report={report} />
      </TabPanel>
    </div>
  );
}
