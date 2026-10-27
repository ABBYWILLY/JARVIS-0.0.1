"""Original, asset-free GLSL sources for the optional GPU reactor prototype."""

FULLSCREEN_VERTEX = """#version 330
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

# A small analytic camera/sphere model is shared by every luminous layer.
# No depth texture or raymarch is needed: rings are ray/plane intersections,
# and the near sphere hit determines whether a world-space stroke is in front.
SPACE_GLSL = """
const float CAMERA_Z = 2.6;
const float CORE_RADIUS = .30;
uniform float u_core_scale, u_orbit_blend;
uniform vec3 u_orbit_phase, u_audio_bands, u_orbit_targets;
float core_radius() { return CORE_RADIUS*(u_core_scale>0.0 ? u_core_scale : 1.0); }
vec2 project_world(vec3 p) { return p.xy * CAMERA_Z / (CAMERA_Z-p.z); }
vec2 scene_plane(vec2 ndc, vec2 size) {
    float aspect = size.x/size.y;
    return ndc*vec2(aspect,1.0)/min(1.0,aspect);
}
vec2 plane_ndc(vec2 p, vec2 size) {
    float aspect = size.x/size.y;
    return p*min(1.0,aspect)/vec2(aspect,1.0);
}
float core_front(vec2 p) {
    float a = dot(p,p)+CAMERA_Z*CAMERA_Z;
    float b = -CAMERA_Z*CAMERA_Z;
    float radius = core_radius();
    float c = CAMERA_Z*CAMERA_Z-radius*radius;
    float discriminant = b*b-a*c;
    return discriminant >= 0.0 ? (-b-sqrt(max(0.0,discriminant)))/a : 10000.0;
}
vec3 rotate_axis(vec3 p,vec3 axis,float angle) {
    float cosine=cos(angle), sine=sin(angle);
    return p*cosine+cross(axis,p)*sine+axis*dot(axis,p)*(1.0-cosine);
}
vec3 orbit_spin_axis(float ring) {
    return normalize(ring<.5 ? vec3(.72,.24,.61)
                    : ring<1.5 ? vec3(-.18,.88,.44) : vec3(.48,-.61,.63));
}
vec4 quaternion_product(vec4 a,vec4 b) {
    return vec4(a.w*b.xyz+b.w*a.xyz+cross(a.xyz,b.xyz),a.w*b.w-dot(a.xyz,b.xyz));
}
vec3 quaternion_rotate(vec4 q,vec3 p) {
    return p+2.0*cross(q.xyz,cross(q.xyz,p)+q.w*p);
}
// Independent world-space rotations around the same origin. Rodrigues keeps
// each basis orthonormal, hence no drift, screen-space orbit or fake wobble.
void orbit_axes(float ring, float time_s, out vec3 axis_u, out vec3 axis_v) {
    float rot = -.34+ring*.13;
    float cosine = .30+ring*.11;
    float sine = sqrt(1.0-cosine*cosine);
    axis_u = vec3(cos(rot),sin(rot),0.0);
    axis_v = vec3(-sin(rot)*cosine,cos(rot)*cosine,sine);
    float phase = ring<.5 ? u_orbit_phase.x : ring<1.5 ? u_orbit_phase.y : u_orbit_phase.z;
    vec3 spin = orbit_spin_axis(ring);
    axis_u = rotate_axis(axis_u,spin,phase);
    axis_v = rotate_axis(axis_v,spin,phase);
    if (u_orbit_blend>0.0) {
        float tilt=acos(cosine)*.5, yaw=rot*.5;
        vec4 base=vec4(cos(yaw)*sin(tilt),sin(yaw)*sin(tilt),
                       sin(yaw)*cos(tilt),cos(yaw)*cos(tilt));
        vec4 turn=vec4(spin*sin(phase*.5),cos(phase*.5));
        vec4 orientation=quaternion_product(turn,base);
        // The target's equivalent quaternion sign is fixed at entry by the
        // adapter. It cannot flip midway through an expression at 180 degrees.
        float sign_=ring<.5 ? u_orbit_targets.x : ring<1.5 ? u_orbit_targets.y : u_orbit_targets.z;
        vec4 target=vec4(0.0,0.0,0.0,sign_<0.0 ? -1.0 : 1.0);
        vec4 aligned=normalize(mix(orientation,target,u_orbit_blend));
        axis_u=quaternion_rotate(aligned,vec3(1.0,0.0,0.0));
        axis_v=quaternion_rotate(aligned,vec3(0.0,1.0,0.0));
    }
}
// Local catalogue paths become points on the visible hemisphere, not a screen
// overlay. The radial limit leaves room for soft strokes inside the silhouette.
vec3 surface_point(vec2 local) {
    vec2 p=vec2(local.x,-local.y)*.78;
    float radius=length(p);
    if (radius>.88) p*=.88/radius;
    return vec3(p,sqrt(max(0.0,1.0-dot(p,p))))*core_radius();
}
float visible_depth(float near_hit, float world_z, float activation) {
    if (activation <= 0.0 || near_hit > 2.0) return 1.0;
    float sample_hit = (CAMERA_Z-world_z)/CAMERA_Z;
    float visible = smoothstep(sample_hit-.0008,sample_hit+.0008,near_hit);
    return mix(1.0,visible,smoothstep(.1,.9,activation));
}
"""

# Orbital bases are uniform across a frame. Evaluate quaternion alignment only
# three times per fullscreen vertex, rather than for every shaded pixel.
REACTOR_VERTEX = """#version 330
out vec2 uv;
flat out vec3 v_orbit_u[3], v_orbit_v[3];
""" + SPACE_GLSL + """
void main() {
    vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);
    uv=p;
    gl_Position=vec4(p*2.0-1.0,0.0,1.0);
    for (int i=0;i<3;++i) orbit_axes(float(i),0.0,v_orbit_u[i],v_orbit_v[i]);
}
"""

# Schlick Fresnel and an angular interference palette are cheap surface terms,
# not a raymarch or a claim of physical refraction through a real environment.
MATERIAL_GLSL = """
float fresnel_view(float ndv) {
    float grazing = 1.0-clamp(ndv,0.0,1.0);
    float square = grazing*grazing;
    return .04+.96*square*square*grazing;
}
vec3 interference_tint(float ndv, vec3 normal, vec3 color) {
    float grazing = 1.0-clamp(ndv,0.0,1.0);
    vec3 blue = vec3(.075,.24,1.1);
    vec3 violet = vec3(.43,.10,.95);
    vec3 cyan = vec3(.12,.9,1.1);
    vec3 tint = mix(blue,violet,smoothstep(.12,.65,grazing));
    tint = mix(tint,cyan,smoothstep(.68,.98,grazing));
    float magenta = smoothstep(.15,.85,-normal.x)*smoothstep(.28,.75,grazing);
    tint = mix(tint,vec3(.75,.12,.74),magenta*.17);
    return mix(tint,color,.22);
}
"""

REACTOR_FRAGMENT = """#version 330
in vec2 uv;
flat in vec3 v_orbit_u[3], v_orbit_v[3];
out vec4 frag;
uniform vec2 u_size;
uniform vec3 u_color;
uniform float u_time, u_reactor, u_rms;
""" + SPACE_GLSL + MATERIAL_GLSL + """
const float TAU = 6.28318530718;
float lineGlow(float d, float width) { return exp(-d*d/(width*width)); }
void main() {
    // Object light is added onto exact black, never an ambient background.
    vec3 light = vec3(0.0);
    if (u_reactor <= 0.0) { frag = vec4(light,1.0); return; }
    vec2 p = scene_plane(uv*2.0-1.0,u_size);
    float r = length(p), t = u_time;
    float activation = smoothstep(0.0,.85,u_reactor);
    float px = 2.0/min(u_size.x,u_size.y);
    float near_hit = core_front(p);
    vec3 cold = mix(u_color,vec3(.53,.83,1.0),.12);
    float radius_core = core_radius();
    float focus = clamp((1.0-u_core_scale)/.08,0.0,1.0);
    float bass=u_audio_bands.x, middle=u_audio_bands.y, treble=u_audio_bands.z;
    float breath = 1.0+.025*sin(t*1.7)+.10*u_rms+.16*middle;
    float silhouette = radius_core*CAMERA_Z/sqrt(CAMERA_Z*CAMERA_Z-radius_core*radius_core);
    // Object-local spill only: no coloured ambient veil or background vignette.
    float spill = lineGlow(r-silhouette,.034+.025*bass)*(1.0-smoothstep(.41,.52,r));
    light += mix(cold,vec3(.32,.19,1.0),.32)*spill*(.13+.14*bass)*activation;
    if (near_hit < 2.0) {
        vec3 surface = vec3(p*near_hit,CAMERA_Z*(1.0-near_hit));
        vec3 normal = normalize(surface);
        vec3 view = normalize(vec3(0.0,0.0,CAMERA_Z)-surface);
        float ndv = max(0.0,dot(normal,view));
        float fresnel = fresnel_view(ndv);
        vec3 spectral = interference_tint(ndv,normal,u_color);
        // Analytic chord length models optical thickness. The back hemisphere
        // supplies a faint refracted-looking field; no scene texture is fetched.
        float chord = 2.0*radius_core*ndv;
        vec3 back = (surface-view*chord)/radius_core;
        vec3 transmission = exp(-vec3(.85,.28,.13)*chord/radius_core);
        float field = sin(back.x*5.4+t*.19+sin(back.y*4.1-t*.13)*.65)
                    +.5*sin(back.z*6.3+back.y*3.0-t*.15);
        float plasma = pow(max(0.0,1.0-abs(field)*.85),3.0);
        float inner = pow(ndv,.55)*(1.0-fresnel);
        // Dark, translucent body; coloured emission stays below the outer skin.
        vec3 body = mix(vec3(.018,.028,.08),spectral*.12,.35);
        body += transmission*mix(vec3(.04,.16,.46),cold*.4,.32)
                *(.045+(.17+.10*focus+.10*middle)*plasma)*inner;
        light += body*breath*activation;
        // Fresnel is angle dependent, with a broad iridescent shoulder and a
        // restrained HDR edge. The centre is intentionally much darker.
        float shoulder = pow(1.0-ndv,1.9);
        light += spectral*(shoulder*.47+fresnel*1.27)*breath*activation;
        vec3 key = normalize(vec3(-.55,.72,.85));
        vec3 fill = normalize(vec3(.8,-.35,.5));
        float key_reflection = pow(max(0.0,dot(normal,normalize(key+view))),72.0);
        float fill_reflection = pow(max(0.0,dot(normal,normalize(fill+view))),38.0);
        float specular = (key_reflection*.60+fill_reflection*.17)*(1.0+.25*treble);
        light += mix(spectral,vec3(.58,.78,1.0),.55)*specular*activation;
    }
    // Stable geometric silhouette, with no serrated carrier or scan-line grid.
    float shell = lineGlow(r-silhouette,.0009+px*.42);
    light += mix(cold,vec3(.32,.18,1.0),.22)*shell*(.48+.15*middle)*activation;
    vec3 ray = vec3(p,-CAMERA_Z);
    // Exact ray/plane intersection: every circle has a world-space depth and
    // perspective foreshortening. Rear portions disappear behind the core.
    for (int i=0;i<3;++i) {
        float fi = float(i);
        vec3 axis_u=v_orbit_u[i], axis_v=v_orbit_v[i];
        vec3 normal = cross(axis_u,axis_v);
        float denominator = dot(normal,ray);
        if (abs(denominator)<.015) continue;
        float hit = -CAMERA_Z*normal.z/denominator;
        if (hit<=0.0) continue;
        vec3 world = vec3(p*hit,CAMERA_Z*(1.0-hit));
        vec2 q = vec2(dot(world,axis_u),dot(world,axis_v));
        float a = atan(q.y,q.x);
        float radius = .48+fi*.11;
        float d = length(q)-radius;
        // Bound derivatives at grazing ray/plane intersections: the
        // singularity must not paint a false halo into empty black space.
        float pixel_width = clamp(fwidth(length(q)),px*.42,px*2.5);
        float depth = clamp(.5+.5*world.z/radius,0.0,1.0);
        float spin = i==0 ? u_orbit_phase.x : i==1 ? u_orbit_phase.y : u_orbit_phase.z;
        float phase = a+spin*1.7+fi;
        float segment = .62+.38*pow(.5+.5*cos(phase),3.0);
        float width = .0008+pixel_width*(.48+depth*.18);
        float rail = lineGlow(d,width)*segment;
        float halo = lineGlow(d,.013+pixel_width)*.085*segment;
        float highlight = pow(max(0.0,cos(phase*2.0+fi)),18.0);
        float packet = pow(max(0.0,cos(phase*3.0+fi)),95.0);
        float visible = visible_depth(near_hit,world.z,u_reactor);
        light += cold*(rail*(.20+depth*.70+highlight*(.28+.24*treble))+halo*.62
                       +lineGlow(d,.004+pixel_width)*packet*(.10+depth*.25))
                      *activation*visible;
    }
    frag = vec4(light,1.0);
}
"""

CURVE_VERTEX = """#version 330
in vec2 a_start, a_end, a_range;
in float a_main;
uniform vec2 u_size;
uniform float u_reactor, u_time, u_rms, u_detail_opacity;
uniform float u_surface_kind, u_surface_amount;
out vec2 v_local;
flat out float v_length, v_strength, v_depth, v_surface;
""" + SPACE_GLSL + """
vec3 position(vec2 source,float u) {
    if (u_surface_kind>0.0) {
        vec3 world=surface_point(source);
        return vec3(plane_ndc(project_world(world),u_size),world.z);
    }
    if (a_main<.5 || u_reactor<=0.0) return vec3(source,.4);
    float a = u*25.13274123-u_time*.32;
    float radius = .024+.17*u;
    vec3 world = vec3(cos(a)*radius,sin(a)*radius*.82,.13*sin(a*.5)+.09);
    vec2 spiral = plane_ndc(project_world(world),u_size);
    float activation = smoothstep(0.0,1.0,u_reactor);
    return vec3(mix(source,spiral,activation),mix(.4,world.z,activation));
}
void main() {
    vec3 first = position(a_start,a_range.x), last = position(a_end,a_range.y);
    vec2 start = first.xy*u_size*.5, end = last.xy*u_size*.5;
    vec2 delta = end-start;
    float length_ = length(delta);
    vec2 tangent = length_>.0001 ? delta/length_ : vec2(1.0,0.0);
    vec2 normal = vec2(-tangent.y,tangent.x);
    float side = (gl_VertexID & 1)==0 ? -1.0 : 1.0;
    float along = gl_VertexID<2 ? -10.0 : length_+10.0;
    vec2 pixel = start+tangent*along+normal*side*10.0;
    gl_Position = vec4(pixel*2.0/u_size,0.0,1.0);
    v_local = vec2(along,side*10.0);
    v_length = length_;
    v_depth = (first.z+last.z)*.5;
    v_surface=float(u_surface_kind>0.0);
    // The supplied PCM/symbol stays authoritative outside the reactor.
    // Its transitional spiral fades away before the sphere takes prominence.
    v_strength = a_main>.5 ? (1.0-smoothstep(.15,.85,u_reactor))
                          : (1.0-smoothstep(0.0,.8,u_reactor))*u_detail_opacity;
    if (u_surface_kind>0.0) {
        // A facial circle is already represented by the physical sphere.
        // Affection retains its complete heart outline; faces use details.
        v_strength=(a_main>.5 && u_surface_kind<1.5 ? 0.0 : u_surface_amount)
                   *(a_main>.5 ? 1.0 : u_detail_opacity);
    }
}
"""

CURVE_FRAGMENT = """#version 330
in vec2 v_local;
flat in float v_length, v_strength, v_depth, v_surface;
uniform vec3 u_color;
uniform vec2 u_size;
uniform float u_rms, u_reactor;
out vec4 frag;
""" + SPACE_GLSL + """
void main() {
    float d = length(vec2(v_local.x-clamp(v_local.x,0.0,v_length),v_local.y));
    float core = exp(-d*d/.62);
    float shoulder = exp(-d*d/3.2)*.26;
    float halo = exp(-d*d/24.0)*.024;
    vec2 p = scene_plane(gl_FragCoord.xy*2.0/u_size-1.0,u_size);
    float near_hit=core_front(p);
    if (v_surface>.5 && near_hit>2.0) discard;
    float visible = v_surface>.5 || u_reactor<=0.0 ? 1.0 : visible_depth(near_hit,v_depth,u_reactor);
    vec3 tint = mix(u_color,vec3(1.0),.16);
    frag = vec4(tint*(core*1.45+shoulder+halo)*(1.0+.4*u_rms)*v_strength*visible,1.0);
}
"""

FILAMENT_VERTEX = """#version 330
uniform vec2 u_size;
uniform float u_time, u_reactor, u_rms;
out vec2 v_local;
flat out float v_length, v_strength, v_depth, v_surface;
""" + SPACE_GLSL + """
const int STEPS = 72;
vec3 path(float u,float strand) {
    float t = u_time;
    float theta = u*6.2831853+strand*1.04719755;
    float a = theta*2.0+t*(.21+strand*.018);
    float radius = .235+.038*sin(theta*3.0+t*.43+strand);
    vec3 p = vec3(cos(a)*radius,sin(a)*radius,.16*sin(theta+strand*.7));
    float tilt = .65+strand*.29;
    p.yz = mat2(cos(tilt),-sin(tilt),sin(tilt),cos(tilt))*p.yz;
    p.xy = mat2(cos(strand*.51),-sin(strand*.51),sin(strand*.51),cos(strand*.51))*p.xy;
    return p;
}
void main() {
    float strand = float(gl_InstanceID/STEPS);
    float u = float(gl_InstanceID%STEPS)/float(STEPS);
    vec3 first = path(u,strand), last = path(u+1.0/float(STEPS),strand);
    vec2 start = plane_ndc(project_world(first),u_size)*u_size*.5;
    vec2 end = plane_ndc(project_world(last),u_size)*u_size*.5;
    vec2 delta = end-start;
    float length_ = length(delta);
    vec2 tangent = normalize(delta+vec2(.00001,0.0));
    vec2 normal = vec2(-tangent.y,tangent.x);
    float side = (gl_VertexID & 1)==0 ? -1.0 : 1.0;
    float along = gl_VertexID<2 ? -5.0 : length_+5.0;
    gl_Position = vec4((start+tangent*along+normal*side*5.0)*2.0/u_size,0.0,1.0);
    v_local = vec2(along,side*5.0);
    v_length = length_;
    v_depth = (first.z+last.z)*.5;
    v_surface=0.0;
    v_strength = u_reactor*u_rms*.08*(.4+.6*pow(.5+.5*sin(u*31.4159-u_time*.7+strand),2.0));
}
"""

PARTICLE_VERTEX = """#version 330
uniform vec2 u_size;
uniform float u_time, u_reactor, u_rms;
out float v_power, v_warm;
flat out float v_depth;
""" + SPACE_GLSL + """
float hash(float n) { return fract(sin(n*127.1+311.7)*43758.5453); }
void main() {
    float id = float(gl_VertexID), seed = hash(id+1.0);
    float trail = mod(id,3.0), packet=floor(id/3.0);
    float ring = mod(packet,3.0);
    float radius = .48+ring*.11;
    float phase = ring<.5 ? u_orbit_phase.x : ring<1.5 ? u_orbit_phase.y : u_orbit_phase.z;
    float a = hash(packet+1.0)*6.2831853+phase*.65-trail*.017;
    vec3 axis_u, axis_v;
    orbit_axes(ring,u_time,axis_u,axis_v);
    vec3 p = radius*(cos(a)*axis_u+sin(a)*axis_v);
    if (mod(packet,4.0)<.5) {
        float latitude=hash(packet+91.0)*2.0-1.0;
        float around=hash(packet+13.0)*6.2831853+phase*.18;
        float shell=.34+hash(packet+27.0)*.10;
        p=vec3(cos(around)*sqrt(1.0-latitude*latitude),latitude,
               sin(around)*sqrt(1.0-latitude*latitude))*shell;
    }
    vec2 projected = plane_ndc(project_world(p),u_size);
    gl_Position = vec4(projected,0.0,1.0);
    // Slow deterministic fades, never random per-frame flicker. Three small
    // points share each orbital packet to form a restrained tapered trail.
    float fade=.5+.5*sin(u_time*.35+hash(packet+81.0)*6.2831853);
    gl_PointSize = (1.25+hash(packet+6.0)*.95)*(1.0+u_rms*.15)*CAMERA_Z/(CAMERA_Z-p.z);
    v_power = (.08+.10*fade)*u_reactor*(.65+p.z)*(1.0-trail*.23)*(1.0-u_orbit_blend*.70);
    v_warm = 0.0;
    v_depth = p.z;
}
"""

PARTICLE_FRAGMENT = """#version 330
in float v_power, v_warm;
flat in float v_depth;
uniform vec3 u_color;
uniform vec2 u_size;
uniform float u_reactor;
out vec4 frag;
""" + SPACE_GLSL + """
void main() {
    vec2 p = gl_PointCoord*2.0-1.0;
    float r2 = dot(p,p);
    if (r2>1.0) discard;
    vec2 screen_p = scene_plane(gl_FragCoord.xy*2.0/u_size-1.0,u_size);
    float visible = visible_depth(core_front(screen_p),v_depth,u_reactor);
    vec3 tint = mix(u_color,vec3(1.0,.53,.24),v_warm*.85);
    frag = vec4(tint*exp(-r2*5.5)*v_power*2.1*visible,1.0);
}
"""

EXTRACT_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
uniform vec2 u_source_size;
out vec4 frag;
void main() {
    vec3 light = vec3(0.0);
    for (int y=0;y<4;++y) for (int x=0;x<4;++x) {
        vec2 offset = (vec2(x,y)-1.5)/u_source_size;
        vec3 c = texture(u_image,uv+offset).rgb;
        float peak = max(c.r,max(c.g,c.b));
        // Selective HDR shoulder: black and sub-threshold midtones cannot
        // lift the entire scene. Reuse the existing quarter-resolution pass.
        float contribution = max(peak-.8,0.0)/max(peak,.0001);
        light += c*contribution*smoothstep(.8,1.4,peak);
    }
    frag = vec4(light/16.0,1.0);
}
"""

BLUR_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
uniform vec2 u_step;
out vec4 frag;
void main() {
    vec3 c = texture(u_image,uv).rgb*.227027;
    c += (texture(u_image,uv+u_step*1.384615).rgb + texture(u_image,uv-u_step*1.384615).rgb)*.316216;
    c += (texture(u_image,uv+u_step*3.230769).rgb + texture(u_image,uv-u_step*3.230769).rgb)*.070270;
    frag = vec4(c,1.0);
}
"""

RESOLVE_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image, u_bloom;
uniform float u_bloom_amount;
out vec4 frag;
void main() {
    vec3 light = texture(u_image,uv).rgb + texture(u_bloom,uv).rgb*u_bloom_amount;
    vec3 mapped = 1.0-exp(-light*.88);
    frag = vec4(pow(max(mapped,vec3(0.0)),vec3(1.0/2.2)),1.0);
}
"""

COPY_FRAGMENT = """#version 330
in vec2 uv;
uniform sampler2D u_image;
out vec4 frag;
void main() { frag = vec4(texture(u_image,uv).rgb,1.0); }
"""
