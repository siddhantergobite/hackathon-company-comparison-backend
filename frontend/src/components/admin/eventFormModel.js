// Conversion between the API event shape and the flat form state used by <EventForm />.

export const EVENT_TYPES = [
  ['conference', 'Conference'], ['meetup', 'Meetup'], ['industry_seminar', 'Industry Seminar'], ['startup_event', 'Startup Event'],
  ['business_networking', 'Business Networking'], ['workshop', 'Workshop'], ['summit', 'Summit'], ['expo', 'Expo'],
  ['trade_show', 'Trade Show'], ['hackathon', 'Hackathon'], ['webinar', 'Webinar'], ['training', 'Training'], ['other', 'Other'],
];

export const BLANK_FORM = {
  title: '', slug: '', event_type: '', summary: '', description: '',
  start_date: '', end_date: '', start_time: '', end_time: '', timezone: '',
  format: 'offline',
  venue: '', address: '', city: '', state: '', country: '', latitude: '', longitude: '',
  categories: [], topics: [], audience: [],
  organizer_name: '', organizer_description: '', organizer_website: '',
  reg_url: '', price: '', currency: '', ticket_type: '', ticket_info: '',
  image_url: '', event_url: '', status: '',
};

const s = (v) => (v === null || v === undefined ? '' : String(v));

export function toForm(e) {
  const loc = e.location || {};
  const org = e.organizer || {};
  const reg = e.registration || {};
  return {
    ...BLANK_FORM,
    title: s(e.title), slug: s(e.slug), event_type: s(e.event_type), summary: s(e.summary), description: s(e.description),
    start_date: s(e.start_date), end_date: s(e.end_date), start_time: s(e.start_time), end_time: s(e.end_time), timezone: s(e.timezone),
    format: e.format || (e.is_online ? 'online' : 'offline'),
    venue: s(loc.venue), address: s(loc.address), city: s(loc.city), state: s(loc.state), country: s(loc.country),
    latitude: s(loc.latitude), longitude: s(loc.longitude),
    categories: e.categories || [], topics: e.topics || [], audience: e.audience || [],
    organizer_name: s(org.name), organizer_description: s(org.description), organizer_website: s(org.website),
    reg_url: s(reg.url), price: s(reg.price), currency: s(reg.currency), ticket_type: s(reg.ticket_type), ticket_info: s(reg.ticket_info),
    image_url: s(e.image_url), event_url: s(e.event_url),
    status: e.status === 'cancelled' || e.status === 'postponed' ? e.status : '',
  };
}

const str = (v) => (String(v).trim() === '' ? null : String(v).trim());
const num = (v) => (String(v).trim() === '' || Number.isNaN(Number(v)) ? null : Number(v));

// Blank text becomes null so that editing can clear a field.
export function toPayload(f, { editing }) {
  const payload = {
    title: f.title.trim(),
    event_type: str(f.event_type),
    summary: str(f.summary),
    description: str(f.description),
    start_date: str(f.start_date),
    end_date: str(f.end_date),
    start_time: str(f.start_time),
    end_time: str(f.end_time),
    timezone: str(f.timezone),
    format: f.format,
    is_online: f.format === 'online',
    location: {
      venue: str(f.venue), address: str(f.address), city: str(f.city), state: str(f.state), country: str(f.country),
      latitude: num(f.latitude), longitude: num(f.longitude),
    },
    categories: f.categories, topics: f.topics, audience: f.audience,
    organizer: { name: str(f.organizer_name), description: str(f.organizer_description), website: str(f.organizer_website) },
    registration: { url: str(f.reg_url), price: num(f.price), currency: str(f.currency), ticket_type: str(f.ticket_type), ticket_info: str(f.ticket_info) },
    image_url: str(f.image_url),
    event_url: str(f.event_url),
    status: str(f.status),
  };
  if (editing && str(f.slug)) payload.slug = str(f.slug);
  return payload;
}

export function validate(f) {
  const errors = {};
  if (f.title.trim().length < 3) errors.title = 'Enter a title (at least 3 characters).';
  if (!f.start_date) errors.start_date = 'Choose a start date.';
  if (f.start_date && f.end_date && f.end_date < f.start_date) errors.end_date = 'End date cannot be before the start date.';
  const lat = f.latitude.trim();
  const lng = f.longitude.trim();
  if ((lat && !lng) || (!lat && lng)) errors.latitude = 'Provide both latitude and longitude, or neither.';
  if (lat && (Number.isNaN(Number(lat)) || Math.abs(Number(lat)) > 90)) errors.latitude = 'Latitude must be between -90 and 90.';
  if (lng && (Number.isNaN(Number(lng)) || Math.abs(Number(lng)) > 180)) errors.longitude = 'Longitude must be between -180 and 180.';
  if (f.price.trim() && (Number.isNaN(Number(f.price)) || Number(f.price) < 0)) errors.price = 'Price must be a positive number.';
  return errors;
}
