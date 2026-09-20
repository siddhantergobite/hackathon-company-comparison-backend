import { useState } from 'react';
import { Pencil, Plus } from 'lucide-react';
import { apiErrorMessage, newsAdminApi } from '../../../api/news';
import { Banner, Button, Card, CardHeader, LoadingPanel, Modal, Tag } from '../../../components/ui';
import TagInput from '../../../components/ui/TagInput';
import { Field } from '../../../components/admin/AdminBits';
import { useApi } from '../../../hooks/useNews';
import { useToast } from '../../../context/ToastContext';

function CategoryModal({ category, saving, error, onSubmit, onClose }) {
  const editing = Boolean(category);
  const [name, setName] = useState(category?.name || '');
  const [icon, setIcon] = useState(category?.icon || '');
  const [keywords, setKeywords] = useState(category?.keywords || []);
  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? `Edit “${category.name}”` : 'Add category'}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="cat-form" loading={saving}>{editing ? 'Save' : 'Add category'}</Button></>}
    >
      <form id="cat-form" className="stack" onSubmit={(e) => { e.preventDefault(); onSubmit({ name: name.trim(), icon: icon.trim() || null, keywords }); }}>
        {error && <Banner tone="error">{error}</Banner>}
        <Field label="Name" htmlFor="c-name" required><input id="c-name" className="input" value={name} onChange={(e) => setName(e.target.value)} disabled={editing} /></Field>
        <Field label="Icon (emoji)" htmlFor="c-icon"><input id="c-icon" className="input" value={icon} maxLength={8} onChange={(e) => setIcon(e.target.value)} placeholder="🎮" /></Field>
        <Field label="Keywords" htmlFor="c-kw" hint="Words or phrases that indicate this category. Press Enter to add. New articles are classified with them immediately.">
          <TagInput id="c-kw" value={keywords} onChange={setKeywords} placeholder="playstation, xbox, esports…" label="Keywords" />
        </Field>
      </form>
    </Modal>
  );
}

export default function NewsCategoriesPage() {
  const toast = useToast();
  const cats = useApi(() => newsAdminApi.categories(), []);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const save = async (body) => {
    setSaving(true);
    setError('');
    try {
      if (editing === 'new') await newsAdminApi.createCategory(body);
      else await newsAdminApi.updateCategory(editing.slug, { icon: body.icon, keywords: body.keywords });
      toast.success(editing === 'new' ? 'Category added.' : 'Category updated.');
      setEditing(null);
      cats.reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };
  const toggle = async (c) => {
    try {
      await newsAdminApi.updateCategory(c.slug, { enabled: !c.enabled });
      toast.success(`${c.name} ${c.enabled ? 'hidden' : 'shown'}.`);
      cats.reload();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  };

  if (cats.loading && !cats.data) return <LoadingPanel title="Loading categories…" />;
  return (
    <div className="stack stack--lg">
      {cats.error && <Banner tone="error">{cats.error}</Banner>}
      <Card flush pad={false}>
        <div style={{ padding: '20px 24px 0' }}>
          <CardHeader title="Categories" actions={<Button size="sm" icon={Plus} onClick={() => { setError(''); setEditing('new'); }}>Add category</Button>} />
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Category</th><th>Slug</th><th>Keywords</th><th>Visible</th><th><span className="sr-only">Edit</span></th></tr></thead>
            <tbody>
              {(cats.data || []).map((c) => (
                <tr key={c.slug}>
                  <td><span aria-hidden="true">{c.icon}</span> <strong>{c.name}</strong>{c.virtual && <Tag tone="neutral"> built-in view</Tag>}</td>
                  <td><code>{c.slug}</code></td>
                  <td className="text-sm muted">{c.virtual ? '—' : `${(c.keywords || []).length} keywords`}</td>
                  <td>
                    {c.virtual ? '—' : (
                      <label className="adm-check"><input type="checkbox" checked={c.enabled !== false} onChange={() => toggle(c)} aria-label={`Show ${c.name}`} /> {c.enabled !== false ? 'Shown' : 'Hidden'}</label>
                    )}
                  </td>
                  <td>{!c.virtual && <button type="button" className="icon-btn icon-btn--sm" title="Edit" aria-label={`Edit ${c.name}`} onClick={() => { setError(''); setEditing(c); }}><Pencil size={15} /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="text-sm muted">Categories are stored in the database, so you can add new ones at any time without a deployment. Already-collected articles keep their category; new ones use the updated keywords.</p>
      {editing && <CategoryModal category={editing === 'new' ? null : editing} saving={saving} error={error} onSubmit={save} onClose={() => setEditing(null)} />}
    </div>
  );
}
