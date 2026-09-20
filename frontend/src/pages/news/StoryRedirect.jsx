import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { newsApi } from '../../api/news';
import { Banner, LinkButton, LoadingPanel } from '../../components/ui';
import { apiErrorMessage } from '../../api/news';

// /news/story/:id opens the story's lead article (the detail page lists every outlet's coverage).
export default function StoryRedirect() {
  const { storyId } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    newsApi
      .story(storyId)
      .then((d) => live && navigate(`/news/${d.story.lead_article_id || d.articles[0]?.id}`, { replace: true }))
      .catch((err) => live && setError(apiErrorMessage(err, 'Story not found')));
    return () => { live = false; };
  }, [storyId, navigate]);

  if (error) {
    return (
      <div className="stack">
        <Banner tone="error" title="Couldn't open that story">{error}</Banner>
        <div><LinkButton to="/news" variant="secondary">Back to News</LinkButton></div>
      </div>
    );
  }
  return <LoadingPanel title="Opening story…" />;
}
